import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

from engram.index import FastEmbedProvider, reciprocal_rank_fusion
from engram.schema import MemoryNote
from tests.helpers import MemoryTestCase


class IndexTests(MemoryTestCase):
    def test_index_deletion_corpus_filters_and_ranking_fallback(self):
        a = self.store.remember("fact", "shared alpha unique")
        native = self.root / "native"
        native.mkdir()
        (native / "n.md").write_text("native alpha unique")
        self.store.index.register_corpus("native", native)
        self.store.index.reconcile()
        local = self.store.index.search("alpha", corpus="local")
        self.assertTrue(local and local[0]["id"] == a.id)
        self.assertTrue(all(x["corpus"] == "native" for x in self.store.index.search("alpha", corpus="native")))
        (self.root / "wiki" / "facts" / f"{a.id}.md").unlink()
        self.store.index.reconcile()
        self.assertFalse(any(x["id"] == a.id for x in self.store.index.search("alpha")))
        self.assertEqual(reciprocal_rank_fusion([["a", "b"], ["b"]])[0], "b")
        self.assertFalse(self.store.index.semantic_available)

    def test_confirmed_local_ranks_before_external_inferred(self):
        shared = self.store.remember("fact", "preferred database sqlite")
        ext = self.root / "orbit"
        ext.mkdir()
        (ext / "x.md").write_text("preferred database sqlite sqlite sqlite")
        self.store.index.register_corpus("orbit", ext)
        self.store.index.reconcile()
        results = self.store.index.search("preferred database sqlite", corpus="all")
        self.assertEqual(results[0]["id"], shared.id)

    def test_recall_excludes_nonconfirmed_local_but_labels_external_evidence(self):
        self.store.remember("fact", "alpha inferred", status="inferred")
        self.store.remember("fact", "alpha conflicted", status="conflicted")
        confirmed = self.store.remember("fact", "alpha confirmed")
        ext = self.root / "external"; ext.mkdir()
        (ext / "e.md").write_text("alpha external evidence")
        self.store.index.register_corpus("orbit", ext)
        rows = self.store.index.search("alpha")
        self.assertEqual([r["id"] for r in rows if r["corpus"] == "local"], [confirmed.id])
        self.assertTrue(all(r["canonical"] is False for r in rows if r["corpus"] != "local"))

    def test_semantic_results_are_fused_and_provider_failure_falls_back(self):
        lexical = self.store.remember("fact", "automobile maintenance")
        semantic = self.store.remember("fact", "vehicle repair")
        class Provider:
            available = True
            def rank(self, query, documents):
                return [d["key"] for d in documents if d["id"] == semantic.id]
        self.store.index.semantic_provider = Provider()
        rows = self.store.index.search("automobile")
        self.assertIn(semantic.id, [r["id"] for r in rows])
        class Broken:
            available = True
            def rank(self, query, documents):
                raise RuntimeError("model unavailable")
        self.store.index.semantic_provider = Broken()
        self.assertEqual(self.store.index.search("automobile")[0]["id"], lexical.id)

    def test_fts_query_punctuation_never_raises_and_empty_uses_semantic(self):
        note = self.store.remember("fact", "cplusplus foo bar user example com operator star")
        for query in ("C++", "foo-bar", "user@example.com", "operator OR", "*"):
            rows = self.store.index.search(query)
            self.assertIsInstance(rows, list)
        class Provider:
            available = True
            def rank(self, query, documents):
                return [d["key"] for d in documents if d["id"] == note.id]
        self.store.index.semantic_provider = Provider()
        self.assertEqual(self.store.index.search("***")[0]["id"], note.id)

    def test_composite_identity_preserves_colliding_external_and_local_ids(self):
        shared = self.store.remember("fact", "collision needle shared", id="same-id")
        ext_tmp = tempfile.TemporaryDirectory(); self.addCleanup(ext_tmp.cleanup)
        ext = Path(ext_tmp.name)
        external = MemoryNote.new("fact", "collision needle external", id="same-id")
        (ext / "same.md").write_text(external.to_markdown())
        self.store.index.register_corpus("orbit", ext)
        rows = self.store.index.search("collision needle")
        collisions = [row for row in rows if row["id"] == "same-id"]
        self.assertEqual(len(collisions), 2)
        self.assertTrue(collisions[0]["canonical"])
        self.assertNotEqual(collisions[0]["key"], collisions[1]["key"])

    def test_fastembed_recall_never_constructs_without_local_artifact(self):
        cache = self.root / "empty-model-cache"
        cache.mkdir(); (cache / "unrelated.bin").write_bytes(b"not the configured model")
        (cache / ".engram-model-ready").touch()
        (cache / "unrelated.bin").unlink()  # Marker alone is not a usable artifact.
        provider = FastEmbedProvider(cache)
        with mock.patch("engram.index.importlib.util.find_spec", return_value=object()), \
             mock.patch.dict(sys.modules, {"fastembed": mock.MagicMock()}):
            provider.rank("query", [{"key":"k", "body":"body"}])
            sys.modules["fastembed"].TextEmbedding.assert_not_called()

    def test_fastembed_rejects_old_constructor_and_wrong_manifest(self):
        import hashlib
        cache = self.root / "model-cache"; cache.mkdir()
        artifact = cache / "model.onnx"; artifact.write_bytes(b"model")
        digest = hashlib.sha256(b"model").hexdigest()
        (cache / ".engram-model.json").write_text(json.dumps({
            "model_name": FastEmbedProvider.MODEL_NAME, "artifacts": {"model.onnx": digest}}))
        class OldEmbedding:
            def __init__(self, model_name, cache_dir):
                raise AssertionError("must not construct")
        module = type("Module", (), {"TextEmbedding": OldEmbedding})
        provider = FastEmbedProvider(cache)
        with mock.patch("engram.index.importlib.util.find_spec", return_value=object()), \
             mock.patch.dict(sys.modules, {"fastembed": module}):
            self.assertFalse(provider.available)
            self.assertEqual(provider.rank("q", [{"key":"k", "body":"b"}]), [])
        (cache / ".engram-model.json").write_text(json.dumps({
            "model_name": "wrong/model", "artifacts": {"model.onnx": digest}}))
        with mock.patch("engram.index.importlib.util.find_spec", return_value=object()), \
             mock.patch.dict(sys.modules, {"fastembed": module}):
            self.assertFalse(provider.available)

    def test_fastembed_accepts_kwargs_constructor_and_forces_local_only(self):
        import hashlib
        cache = self.root / "kwargs-model-cache"; cache.mkdir()
        artifact = cache / "model.onnx"; artifact.write_bytes(b"model")
        digest = hashlib.sha256(b"model").hexdigest()
        (cache / ".engram-model.json").write_text(json.dumps({
            "model_name": FastEmbedProvider.MODEL_NAME, "artifacts": {"model.onnx": digest}}))
        calls = []
        class KwargsEmbedding:
            def __init__(self, model_name, cache_dir, **kwargs):
                calls.append(kwargs)
            def embed(self, texts):
                return [[1.0, 0.0] for _ in texts]
        module = type("Module", (), {"TextEmbedding": KwargsEmbedding})
        provider = FastEmbedProvider(cache)
        with mock.patch("engram.index.importlib.util.find_spec", return_value=object()), \
             mock.patch.dict(sys.modules, {"fastembed": module}):
            self.assertTrue(provider.available)
            self.assertEqual(provider.rank("q", [{"key":"k", "body":"b"}]), ["k"])
        self.assertEqual(calls, [{"local_files_only": True}])

    def test_corpus_include_pattern_filters_claude_memory(self):
        claude = self.root / "claude"
        (claude / "project" / "memory").mkdir(parents=True)
        (claude / "project" / "memory" / "keep.md").write_text("needle keep")
        (claude / "project" / "transcript.md").write_text("needle leak")
        self.store.index.register_corpus("native", claude, include_pattern="*/memory/*.md")
        rows = self.store.index.search("needle", corpus="native")
        self.assertEqual(len(rows), 1)
        self.assertIn("keep", rows[0]["body"])


if __name__ == "__main__":
    unittest.main()
