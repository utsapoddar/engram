from __future__ import annotations

import hashlib
import importlib.util
from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time
import math
import inspect
import json
import hashlib
import re
import os

from .config import LOCAL_CORPUS
from .schema import parse_note
from .io import repository_lock
from .transactions import recover_correction_unlocked


class FastEmbedProvider:
    """Lazy optional semantic ranker; no model or dependency is loaded at startup."""
    MODEL_NAME = "BAAI/bge-small-en-v1.5"

    def __init__(self, cache_dir: Path):
        self._model = None
        self.cache_dir = Path(cache_dir)

    def _has_local_artifact(self):
        manifest_path = self.cache_dir / ".engram-model.json"
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, json.JSONDecodeError):
            return False
        if manifest.get("model_name") != self.MODEL_NAME or not isinstance(manifest.get("artifacts"), dict) or not manifest["artifacts"]:
            return False
        for relative, expected in manifest["artifacts"].items():
            if not isinstance(relative, str) or not isinstance(expected, str):
                return False
            artifact = (self.cache_dir / relative).resolve()
            if self.cache_dir.resolve() not in artifact.parents or not artifact.is_file():
                return False
            if hashlib.sha256(artifact.read_bytes()).hexdigest() != expected:
                return False
        return True

    @property
    def available(self):
        if importlib.util.find_spec("fastembed") is None or not self._has_local_artifact():
            return False
        try:
            from fastembed import TextEmbedding
            parameters = inspect.signature(TextEmbedding).parameters
            return "local_files_only" in parameters or any(
                parameter.kind is inspect.Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
        except (ImportError, TypeError, ValueError):
            return False

    def rank(self, query: str, documents: list[dict]) -> list[str]:
        if not self.available:
            return []
        if self._model is None:
            from fastembed import TextEmbedding
            self._model = TextEmbedding(model_name=self.MODEL_NAME, cache_dir=str(self.cache_dir),
                                        local_files_only=True)
        vectors = list(self._model.embed([query] + [d["body"] for d in documents]))
        query_vector = vectors[0]
        def cosine(vector):
            dot = sum(a * b for a, b in zip(query_vector, vector))
            denom = math.sqrt(sum(a * a for a in query_vector) * sum(b * b for b in vector))
            return dot / denom if denom else 0.0
        ranked = sorted(zip(documents, vectors[1:]), key=lambda item: cosine(item[1]), reverse=True)
        return [document["key"] for document, _ in ranked]


def reciprocal_rank_fusion(rankings: list[list[str]], k: int = 60) -> list[str]:
    scores: dict[str, float] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking, 1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + rank)
    return sorted(scores, key=lambda item: (-scores[item], item))


class MemoryIndex:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.state = self.root / "state"
        self.state.mkdir(parents=True, exist_ok=True)
        self.db_path = self.state / "memory.sqlite3"
        self.corpora: dict[str, list[tuple[Path, str | None]]] = {LOCAL_CORPUS: [(self.root, None)]}
        self.semantic_provider = FastEmbedProvider(self.state / "models")
        self._initialize()

    @contextmanager
    def _connect(self):
        con = None
        try:
            con = sqlite3.connect(self.db_path, timeout=30)
            con.execute("PRAGMA journal_mode=WAL")
            with con:
                yield con
        finally:
            if con is not None:
                con.close()

    def _initialize(self):
        with repository_lock(self.root):
            try:
                self._initialize_unlocked()
            except sqlite3.DatabaseError:
                self._quarantine_unlocked()
                self._initialize_unlocked()

    def _initialize_unlocked(self):
        with self._connect() as con:
            con.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memories USING fts5(id UNINDEXED, corpus UNINDEXED, path UNINDEXED, type UNINDEXED, status UNINDEXED, body)")
            con.execute("CREATE TABLE IF NOT EXISTS indexed_files(path PRIMARY KEY, digest NOT NULL)")
            con.execute("CREATE TABLE IF NOT EXISTS metadata(key PRIMARY KEY, value)")

    def _quarantine_unlocked(self):
        suffix = f".corrupt-{time.time_ns()}"
        for path in (self.db_path, Path(f"{self.db_path}-wal"), Path(f"{self.db_path}-shm")):
            if path.exists():
                os.replace(path, Path(f"{path}{suffix}"))

    @property
    def semantic_available(self):
        return bool(self.semantic_provider.available)

    def register_corpus(self, name: str, root: Path, *, include_pattern: str | None = None):
        path = Path(root)
        self.corpora.setdefault(name, [])
        entry = (path, include_pattern)
        if entry not in self.corpora[name]:
            self.corpora[name].append(entry)

    def _documents(self):
        for corpus, roots in self.corpora.items():
            for root, include_pattern in roots:
                if not root.exists():
                    continue
                paths = root.glob(include_pattern) if include_pattern else root.rglob("*.md")
                for path in paths:
                    if "state" in path.parts or path.name == "hot.md":
                        continue
                    yield corpus, path

    def reconcile(self):
        with repository_lock(self.root):
            recover_correction_unlocked(self.root)
            try:
                self._reconcile_unlocked()
            except sqlite3.DatabaseError:
                self._quarantine_unlocked()
                self._initialize_unlocked()
                self._reconcile_unlocked()

    def _reconcile_unlocked(self):
        current = set()
        with self._connect() as con:
            for corpus, path in self._documents():
                key = f"{corpus}:{path.resolve()}"
                text = path.read_text(errors="replace")
                digest = hashlib.sha256(text.encode()).hexdigest()
                note_id, type_, status, body = hashlib.sha256(key.encode()).hexdigest()[:24], "fact", "inferred", text
                try:
                    note = parse_note(text)
                    if (corpus == LOCAL_CORPUS and path.is_relative_to(self.root / "wiki")
                            and path.name != "index.md" and path.stem != note.id):
                        continue
                    note_id, type_, status, body = note.id, note.type, note.status, note.body
                except (ValueError, TypeError):
                    pass
                current.add(key)
                old = con.execute("SELECT digest FROM indexed_files WHERE path=?", (key,)).fetchone()
                if old and old[0] == digest:
                    continue
                con.execute("DELETE FROM memories WHERE path=?", (key,))
                con.execute("INSERT INTO memories(id,corpus,path,type,status,body) VALUES(?,?,?,?,?,?)",
                            (note_id, corpus, key, type_, status, body))
                con.execute("INSERT OR REPLACE INTO indexed_files(path,digest) VALUES(?,?)", (key, digest))
            known = {row[0] for row in con.execute("SELECT path FROM indexed_files")}
            for deleted in known - current:
                con.execute("DELETE FROM memories WHERE path=?", (deleted,))
                con.execute("DELETE FROM indexed_files WHERE path=?", (deleted,))
            con.execute("INSERT OR REPLACE INTO metadata(key,value) VALUES('last_reconcile',?)", (str(time.time()),))

    def search(self, query: str, *, corpus: str = "all", limit: int = 20, confirmed_only: bool = True):
        self.reconcile()
        tokens = re.findall(r"\w+", query, flags=re.UNICODE)
        terms = " OR ".join(f'"{token}"' for token in tokens)
        filters, filter_params = [], []
        if corpus != "all":
            filters.append("corpus=?")
            filter_params.append(corpus)
        if confirmed_only:
            filters.append(f"(corpus != '{LOCAL_CORPUS}' OR status='confirmed')")
        where = " AND ".join(filters) or "1=1"
        with self._connect() as con:
            eligible_rows = con.execute(f"SELECT id,corpus,path,type,status,body FROM memories WHERE {where}", filter_params).fetchall()
            lexical_rows = (con.execute(
                f"SELECT id,corpus,path,bm25(memories) FROM memories WHERE memories MATCH ? AND {where}",
                [terms] + filter_params).fetchall() if terms else [])
        documents = [{"id": r[0], "corpus": r[1], "path": r[2], "type": r[3], "status": r[4],
                      "body": r[5], "canonical": r[1] == LOCAL_CORPUS and r[4] == "confirmed",
                      "key": f"{r[1]}\0{r[2]}\0{r[0]}"} for r in eligible_rows]
        by_key = {row["key"]: row for row in documents}
        lexical_keys = [f"{row[1]}\0{row[2]}\0{row[0]}" for row in sorted(lexical_rows, key=lambda row: row[3])]
        rankings = [lexical_keys]
        try:
            semantic_keys = [key for key in self.semantic_provider.rank(query, documents) if key in by_key]
            if semantic_keys:
                rankings.append(semantic_keys)
        except Exception:
            pass
        fused = reciprocal_rank_fusion(rankings)
        rank = {id_: position for position, id_ in enumerate(fused)}
        results = [by_key[key] for key in fused if key in by_key]
        results.sort(key=lambda row: (0 if row["canonical"] else 1, rank[row["key"]]))
        return results[:limit]

    def integrity_ok(self):
        with repository_lock(self.root):
            try:
                with self._connect() as con:
                    if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                        raise sqlite3.DatabaseError("integrity check failed")
                return True
            except sqlite3.DatabaseError:
                self._quarantine_unlocked()
                self._initialize_unlocked()
                self._reconcile_unlocked()
                return True

    def age_seconds(self):
        with self._connect() as con:
            row = con.execute("SELECT value FROM metadata WHERE key='last_reconcile'").fetchone()
        return None if not row else max(0.0, time.time() - float(row[0]))
