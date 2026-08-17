import re
import subprocess
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FORBIDDEN = re.compile(
    r"(?:/(?:Users|home)/[^/\s]+/|[A-Z0-9._%+-]+@(?!example\.com\b)[A-Z0-9.-]+\.[A-Z]{2,})",
    re.IGNORECASE,
)


class DemoTest(unittest.TestCase):
    def test_generated_runtime_artifacts_can_never_be_committed(self):
        """Bytecode embeds absolute build paths, so it must be unstageable.

        Asserting these files are *absent* cannot work: importing this very
        module writes tests/__pycache__, so such a test fails itself. The
        durable invariant is that they are ignored, not that they never exist.
        """
        ignored = (REPO / ".gitignore").read_text()
        for pattern in ("__pycache__/", "*.py[cod]", "state/", "demo/.scratch/"):
            self.assertIn(pattern, ignored, f"{pattern} must be gitignored")

    def test_seed_corpus_exists_and_covers_all_types(self):
        notes = list((REPO / "demo" / "seed").glob("*.md"))
        self.assertGreaterEqual(len(notes), 15)
        types = {t for note in notes
                 for t in re.findall(r'^type:\s*"(\w+)"', note.read_text(), re.M)}
        self.assertEqual(types, {"preference", "decision", "project_state",
                                 "environment", "pattern", "failure", "fact"})

    def test_seed_corpus_contains_no_real_identifiers(self):
        for note in (REPO / "demo" / "seed").glob("*.md"):
            self.assertIsNone(FORBIDDEN.search(note.read_text()),
                              f"forbidden identifier in {note.name}")

    def test_shipped_warm_example_parses_with_the_real_code(self):
        """The documented format must be the format the engine actually reads."""
        import shutil
        import sys
        import tempfile

        sys.path.insert(0, str(REPO / "src"))
        from engram.maintenance import process_warm_actions

        example = REPO / "warm.md.example"
        self.assertTrue(example.is_file(), "warm.md.example must ship")
        self.assertIsNone(FORBIDDEN.search(example.read_text()))

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copy(example, root / "warm.md")
            # Far-future due dates mean nothing is urgent yet; the point is that
            # the shipped example parses without raising.
            self.assertIsInstance(process_warm_actions(root), list)

    def test_walkthrough_runs_clean(self):
        result = subprocess.run(["bash", str(REPO / "demo" / "walkthrough.sh")],
                                capture_output=True, text=True, timeout=180)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("superseded", result.stdout)


if __name__ == "__main__":
    unittest.main()
