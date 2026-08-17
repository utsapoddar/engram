import unittest

from engram.maintenance import lint_repository, maintain_repository, repository_status
from engram.schema import MemoryNote, NoteValidationError, parse_note
from tests.helpers import MemoryTestCase


class SchemaTests(MemoryTestCase):
    def test_schema_statuses_and_round_trip(self):
        note = MemoryNote.new("preference", "Use structured log output", tags=["style"])
        self.assertEqual(note.status, "confirmed")
        self.assertEqual(parse_note(note.to_markdown()).id, note.id)
        with self.assertRaises(ValueError):
            MemoryNote.new("unknown", "bad")
        with self.assertRaises(ValueError):
            MemoryNote.new("fact", "bad", status="maybe")

    def test_schema_rejects_malformed_notes_consistently_and_lint_reports(self):
        malformed = [
            "---\nid: \"../bad\"\ntype: \"fact\"\nstatus: \"confirmed\"\ncreated_at: \"nope\"\nupdated_at: \"nope\"\nlast_verified: null\nsource_refs: []\ntags: []\n---\nx",
            "---\nid: \"ok\"\ntype: \"fact\"\nstatus: \"confirmed\"\ncreated_at: \"2000-01-01T00:00:00+00:00\"\nupdated_at: \"2000-01-01T00:00:00+00:00\"\nlast_verified: null\nsource_refs: \"bad\"\ntags: []\n---\nx",
            "---\nid: \"missing-fields\"\n---\nx",
            "---\nid: \"bad-type\"\ntype: []\nstatus: \"confirmed\"\ncreated_at: \"2000-01-01T00:00:00+00:00\"\nupdated_at: \"2000-01-01T00:00:00+00:00\"\nlast_verified: null\nsource_refs: []\ntags: []\n---\nx",
        ]
        for text in malformed:
            with self.assertRaises(NoteValidationError):
                parse_note(text)
        with self.assertRaises(NoteValidationError):
            MemoryNote("bad", [], "confirmed", "2000-01-01T00:00:00+00:00",
                       "2000-01-01T00:00:00+00:00", None, [], [], "x")
        bad = self.root / "wiki" / "facts" / "malformed.md"; bad.write_text(malformed[0])
        failures = lint_repository(self.root)
        self.assertTrue(any("malformed.md" in failure for failure in failures))
        maintain_repository(self.root, self.store.index)
        self.assertEqual(repository_status(self.root, self.store.index)["overall"], "stale")


if __name__ == "__main__":
    unittest.main()
