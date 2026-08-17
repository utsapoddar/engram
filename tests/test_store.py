import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest import mock

from engram.maintenance import lint_repository
from engram.schema import MemoryNote, parse_note
from tests.helpers import MemoryTestCase


class StoreTests(MemoryTestCase):
    def test_correction_supersedes_and_forget_tombstones(self):
        old = self.store.remember("decision", "Use SQLite")
        replacement = self.store.correct(old.id, "Use SQLite FTS5")
        self.assertEqual(self.store.get(old.id).status, "superseded")
        self.assertIn(old.id, replacement.source_refs)
        self.store.forget(replacement.id, "obsolete")
        forgotten = self.store.get(replacement.id)
        self.assertEqual(forgotten.status, "superseded")
        self.assertIn("obsolete", forgotten.body)

    def test_idempotent_capture_and_no_transcript_copy(self):
        transcript = self.root / "session.jsonl"
        transcript.write_text('\n'.join([
            json.dumps({"role": "user", "content": "Please choose SQLite"}),
            json.dumps({"role": "assistant", "content": "Decision: use SQLite FTS5"}),
        ]))
        first = self.store.capture_session("codex", transcript)
        second = self.store.capture_session("codex", transcript)
        self.assertEqual(first.id, second.id)
        saved = (self.root / "raw" / "sessions" / f"{first.id}.md").read_text()
        self.assertIn("Decision: use SQLite FTS5", saved)
        self.assertNotIn(transcript.read_text(), saved)

    def test_capture_real_claude_and_codex_nested_jsonl(self):
        claude = self.root / "claude.jsonl"
        claude.write_text('\n'.join([
            json.dumps({"type":"user","message":{"role":"user","content":[{"type":"text","text":"Claude user"}]}}),
            json.dumps({"type":"assistant","message":{"role":"assistant","content":[{"type":"thinking","thinking":"secret thought"},{"type":"text","text":"Claude visible"}]}}),
        ]))
        codex = self.root / "codex.jsonl"
        codex.write_text('\n'.join([
            json.dumps({"type":"response_item","payload":{"type":"message","role":"user","content":[{"type":"input_text","text":"Codex user"}]}}),
            json.dumps({"type":"response_item","payload":{"type":"message","role":"assistant","content":[{"type":"output_text","text":"Codex visible"}]}}),
        ]))
        c1 = self.store.capture_session("claude", claude).body
        c2 = self.store.capture_session("codex", codex).body
        self.assertIn("Claude user", c1); self.assertIn("Claude visible", c1)
        self.assertNotIn("secret thought", c1)
        self.assertIn("Codex user", c2); self.assertIn("Codex visible", c2)

    def test_capture_hashes_and_parses_one_immutable_byte_snapshot(self):
        transcript = self.root / "mutating.jsonl"
        original = json.dumps({"role":"assistant", "content":"original visible"}).encode()
        appended = json.dumps({"role":"assistant", "content":"later mutation"}).encode()
        transcript.write_bytes(original)
        real_read_bytes = Path.read_bytes
        def mutate_after_read(path):
            data = real_read_bytes(path)
            if path == transcript:
                with path.open("ab") as handle:
                    handle.write(b"\n" + appended)
            return data
        with mock.patch.object(Path, "read_bytes", mutate_after_read):
            note = self.store.capture_session("codex", transcript)
        self.assertIn("original visible", note.body)
        self.assertNotIn("later mutation", note.body)
        expected = __import__("hashlib").sha256(b"codex\0" + original).hexdigest()[:24]
        self.assertEqual(note.id, expected)

    def test_cli_json_and_status(self):
        env = {**os.environ, "ENGRAM_ROOT": str(self.root), "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
        remember = subprocess.run(
            [sys.executable, "-m", "engram.cli", "remember", "--type", "fact", "--stdin", "--json"],
            input="CLI memory", text=True, capture_output=True, env=env, check=True)
        note_id = json.loads(remember.stdout)["id"]
        recall = subprocess.run([sys.executable, "-m", "engram.cli", "recall", "CLI", "--json"],
                                text=True, capture_output=True, env=env, check=True)
        self.assertEqual(json.loads(recall.stdout)[0]["id"], note_id)
        status = subprocess.run([sys.executable, "-m", "engram.cli", "status", "--json"],
                                text=True, capture_output=True, env=env, check=True)
        self.assertIn("embedding_available", json.loads(status.stdout))

    def test_ids_are_safe_unique_and_exact_across_types(self):
        self.store.remember("fact", "first", id="global-id")
        with self.assertRaises(ValueError):
            self.store.remember("decision", "collision", id="global-id")
        for unsafe in ("../global-id", "*", "[abc]", "a/b"):
            with self.assertRaises(ValueError):
                self.store.get(unsafe)
            with self.assertRaises(ValueError):
                self.store.forget(unsafe, "bad")
            with self.assertRaises(ValueError):
                self.store.correct(unsafe, "bad")

    def test_filename_and_frontmatter_id_mismatch_is_rejected_and_not_indexed(self):
        mismatched = MemoryNote.new("fact", "mismatch search needle", id="frontmatter-id")
        path = self.root / "wiki" / "facts" / "requested-id.md"
        path.write_text(mismatched.to_markdown())
        with self.assertRaises(ValueError):
            self.store.get("requested-id")
        with self.assertRaises(ValueError):
            self.store.correct("requested-id", "replacement")
        with self.assertRaises(ValueError):
            self.store.forget("requested-id", "obsolete")
        self.assertEqual(parse_note(path.read_text()).status, "confirmed")
        self.assertTrue(any("filename id mismatch" in failure for failure in lint_repository(self.root)))
        self.store.index.reconcile()
        self.assertFalse(any(row["id"] == "frontmatter-id" for row in self.store.index.search("mismatch needle")))


if __name__ == "__main__":
    unittest.main()
