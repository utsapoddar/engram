import threading
import time
import unittest
from unittest import mock

from engram.schema import parse_note
from tests.helpers import MemoryTestCase


class TransactionsTests(MemoryTestCase):
    def test_correction_journal_recovers_before_recall(self):
        old = self.store.remember("decision", "old truth")
        original = self.store._atomic_write
        calls = 0
        def flaky(path, content):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("disk full")
            return original(path, content)
        with mock.patch.object(self.store, "_atomic_write", side_effect=flaky):
            with self.assertRaises(OSError):
                self.store.correct(old.id, "new truth")
        self.assertTrue((self.root / "state" / "correction-journal.json").exists())
        replacements = [parse_note(p.read_text()) for p in (self.root / "wiki" / "decisions").glob("*.md") if p.stem != old.id]
        self.assertEqual(len(replacements), 1)
        self.assertEqual(replacements[0].status, "confirmed")
        rows = self.store.index.search("new truth")  # Recall automatically recovers the journal.
        self.assertEqual(rows[0]["id"], replacements[0].id)
        self.assertFalse((self.root / "state" / "correction-journal.json").exists())
        self.assertEqual(self.store.get(old.id).status, "superseded")
        self.assertEqual(self.store.get(replacements[0].id).status, "confirmed")

    def test_concurrent_corrections_create_exactly_one_replacement(self):
        old = self.store.remember("decision", "single source truth")
        barrier = threading.Barrier(8)
        successes, errors = [], []
        def correct(i):
            barrier.wait()
            try:
                successes.append(self.store.correct(old.id, f"replacement {i}"))
            except ValueError as exc:
                errors.append(exc)
        threads = [threading.Thread(target=correct, args=(i,)) for i in range(8)]
        [thread.start() for thread in threads]
        [thread.join() for thread in threads]
        confirmed = [parse_note(path.read_text()) for path in (self.root / "wiki" / "decisions").glob("*.md")
                     if parse_note(path.read_text()).status == "confirmed"]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(errors), 7)
        self.assertEqual(len(confirmed), 1)
        self.assertEqual(confirmed[0].id, successes[0].id)

    def test_reconcile_lock_prevents_transient_correction_visibility(self):
        old = self.store.remember("decision", "before interleaving")
        started, release, corrected = threading.Event(), threading.Event(), threading.Event()
        real_documents = self.store.index._documents
        first = [True]
        def paused_documents():
            if first[0]:
                first[0] = False
                started.set()
                release.wait(timeout=5)
            yield from real_documents()
        def reconcile():
            self.store.index.reconcile()
        def correct():
            self.store.correct(old.id, "after interleaving")
            corrected.set()
        with mock.patch.object(self.store.index, "_documents", side_effect=paused_documents):
            scan_thread = threading.Thread(target=reconcile); scan_thread.start()
            self.assertTrue(started.wait(timeout=2))
            correction_thread = threading.Thread(target=correct); correction_thread.start()
            time.sleep(0.1)
            self.assertFalse(corrected.is_set())
            self.assertEqual(parse_note((self.root / "wiki" / "decisions" / f"{old.id}.md").read_text()).status, "confirmed")
            release.set()
            scan_thread.join(timeout=5); correction_thread.join(timeout=5)
        self.assertTrue(corrected.is_set())


if __name__ == "__main__":
    unittest.main()
