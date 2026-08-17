import tempfile
import unittest
from pathlib import Path

from engram.store import MemoryStore


class MemoryTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.store = MemoryStore(self.root)

    def tearDown(self):
        self.tmp.cleanup()
