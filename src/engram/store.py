from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .index import MemoryIndex
from .io import atomic_write, repository_lock
from .sanitize import sanitize_text
from .schema import MemoryNote, NoteValidationError, parse_note, utcnow, validate_id
from .transactions import (clear_correction_journal, correction_record, journal_path,
                           recover_correction, recover_correction_unlocked)

TYPE_DIRS = {
    "preference": "preferences", "decision": "decisions", "project_state": "projects",
    "environment": "environment", "pattern": "patterns", "failure": "failures", "fact": "facts",
}


class MemoryStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        for directory in ["raw/sessions", "wiki/preferences", "wiki/projects", "wiki/decisions",
                          "wiki/patterns", "wiki/failures", "wiki/environment", "wiki/facts", "state"]:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        recover_correction(self.root)
        self.index = MemoryIndex(self.root)

    def _lock(self):
        return repository_lock(self.root)

    def _path(self, note: MemoryNote):
        return self.root / "wiki" / TYPE_DIRS[note.type] / f"{note.id}.md"

    @staticmethod
    def _atomic_write(path: Path, content: str):
        atomic_write(path, content)

    def _find_path_unlocked(self, id: str):
        validate_id(id)
        for directory in dict.fromkeys(TYPE_DIRS.values()):
            path = self.root / "wiki" / directory / f"{id}.md"
            if path.is_file():
                return path
        return None

    def _save(self, note: MemoryNote, *, create_only=False):
        with self._lock():
            if create_only and self._find_path_unlocked(note.id):
                raise ValueError(f"memory id already exists: {note.id}")
            self._atomic_write(self._path(note), note.to_markdown())
        self.index.reconcile()
        return note

    def remember(self, type: str, body: str, *, status="confirmed", source_refs=None, tags=None, id=None):
        return self._save(MemoryNote.new(type, sanitize_text(body), status=status,
                                         source_refs=source_refs, tags=tags, id=id), create_only=True)

    def _get_unlocked(self, id: str):
        path = self._find_path_unlocked(id)
        if path is None:
            raise KeyError(id)
        note = parse_note(path.read_text())
        if path.stem != note.id or note.id != id:
            raise NoteValidationError(f"filename id mismatch: {path.stem} != {note.id}")
        return note

    def get(self, id: str):
        return self._get_unlocked(id)

    def correct(self, id: str, body: str):
        with self._lock():
            recover_correction_unlocked(self.root)
            old = self._get_unlocked(id)
            if old.status == "superseded":
                raise ValueError(f"memory {id} is already superseded")
            old.status, old.updated_at = "superseded", utcnow()
            replacement = MemoryNote.new(old.type, sanitize_text(body), source_refs=[id],
                                         tags=list(dict.fromkeys(old.tags + ["correction"])))
            if self._find_path_unlocked(replacement.id):
                raise ValueError(f"memory id already exists: {replacement.id}")
            record = correction_record(self.root, self._path(old), self._path(replacement),
                                       old.to_markdown(), replacement.to_markdown(), old.id, replacement.id)
            self._atomic_write(journal_path(self.root), record)
            # Confirm replacement first. A crash may temporarily leave two truths,
            # while the durable journal makes recall finish the transaction.
            self._atomic_write(self._path(replacement), replacement.to_markdown())
            self._atomic_write(self._path(old), old.to_markdown())
            clear_correction_journal(self.root)
        self.index.reconcile()
        return replacement

    def forget(self, id: str, reason: str):
        note = self.get(id)
        note.status, note.updated_at = "superseded", utcnow()
        note.body = f"Forgotten: {sanitize_text(reason, max_chars=500)}"
        return self._save(note)

    def capture_session(self, agent: str, transcript: Path):
        path = Path(transcript)
        transcript_bytes = path.read_bytes()
        digest = hashlib.sha256((agent + "\0").encode() + transcript_bytes).hexdigest()[:24]
        destination = self.root / "raw" / "sessions" / f"{digest}.md"
        if destination.exists():
            return parse_note(destination.read_text())
        last = {"user": "", "assistant": ""}
        for line in transcript_bytes.decode(errors="replace").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = row.get("message") or row.get("payload") or row
            if message.get("type") == "message" or "role" in message:
                role = message.get("role")
                content = message.get("content", "")
                if isinstance(content, str):
                    visible = content
                elif isinstance(content, list):
                    visible = "\n".join(str(item.get("text", "")) for item in content
                                        if isinstance(item, dict) and item.get("type") in {"text", "input_text", "output_text"})
                else:
                    visible = ""
                if role in last and visible:
                    last[role] = visible
        body = sanitize_text(f"Agent: {agent}\nSource: {path.name}\nLast user: {last['user'][:800]}\nLast assistant: {last['assistant'][:1200]}")
        note = MemoryNote.new("project_state", body, status="inferred", source_refs=[str(path)],
                              tags=["captured-session"], id=digest)
        with self._lock():
            if not destination.exists():
                self._atomic_write(destination, note.to_markdown())
        self.index.reconcile()
        return note
