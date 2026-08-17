import threading
import unittest

from tests.helpers import MemoryTestCase


class IoTests(MemoryTestCase):
    def test_atomic_concurrent_writes(self):
        errors = []
        def write(i):
            try:
                self.store.remember("fact", f"fact {i}")
            except Exception as exc:
                errors.append(exc)
        threads = [threading.Thread(target=write, args=(i,)) for i in range(12)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(errors, [])
        self.assertEqual(len(list((self.root / "wiki" / "facts").glob("*.md"))), 12)


if __name__ == "__main__":
    unittest.main()
