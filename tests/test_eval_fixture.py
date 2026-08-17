import json
import unittest
from pathlib import Path

from engram.eval import run_eval
from engram.store import MemoryStore
import tempfile


class EvalHarnessTests(unittest.TestCase):
    def test_fixture_has_at_least_twenty_queries(self):
        fixture = json.loads((Path(__file__).parent / "fixtures" / "eval_queries.json").read_text())
        rows = fixture["cases"]
        self.assertGreaterEqual(len(rows), 20)
        self.assertTrue(all({"id", "body", "query", "expected_id"} <= row.keys() for row in rows))
        self.assertGreaterEqual(len(fixture["distractors"]), 10)
        self.assertTrue(all(row["query"].lower() != row["body"].lower() for row in rows))
        self.assertFalse(any("retrievalkey" in row["query"].lower() or "retrievalkey" in row["body"].lower() for row in rows))

    def test_seeded_retrieval_eval_recall_at_five(self):
        with tempfile.TemporaryDirectory() as tmp:
            score = run_eval(MemoryStore(Path(tmp)), Path(__file__).parent / "fixtures" / "eval_queries.json")
        self.assertGreaterEqual(score["recall_at_5"], 0.90)
        self.assertEqual(score["queries"], 20)
