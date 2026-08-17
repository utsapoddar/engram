import os
import tempfile
import unittest
from pathlib import Path

from engram.config import LOCAL_CORPUS, Corpus, load_config


class ConfigTest(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.root = Path(self._dir.name)
        self._env = dict(os.environ)
        os.environ.pop("ENGRAM_ROOT", None)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self._env)
        self._dir.cleanup()

    def test_local_corpus_name_is_stable(self):
        self.assertEqual(LOCAL_CORPUS, "local")

    def test_defaults_to_given_root_with_no_config_file(self):
        local, external = load_config(self.root)
        self.assertEqual(local, self.root)
        self.assertEqual(external, [])

    def test_env_var_overrides_root(self):
        os.environ["ENGRAM_ROOT"] = str(self.root / "elsewhere")
        local, _ = load_config(None)
        self.assertEqual(local, self.root / "elsewhere")

    def test_reads_named_corpora_from_toml(self):
        (self.root / "engram.toml").write_text(
            '[corpora.work]\n'
            f'path = "{self.root}/work"\n'
            'include_pattern = "*/memory/*.md"\n'
        )
        local, external = load_config(self.root)
        self.assertEqual(local, self.root)
        self.assertEqual(len(external), 1)
        self.assertEqual(external[0], Corpus("work", self.root / "work", "*/memory/*.md"))

    def test_include_pattern_is_optional(self):
        (self.root / "engram.toml").write_text(
            f'[corpora.notes]\npath = "{self.root}/notes"\n'
        )
        _, external = load_config(self.root)
        self.assertIsNone(external[0].include_pattern)

    def test_corpus_paths_expand_user(self):
        (self.root / "engram.toml").write_text(
            '[corpora.home]\npath = "~/notes"\n'
        )
        _, external = load_config(self.root)
        self.assertEqual(external[0].path, Path("~/notes").expanduser())

    def test_rejects_corpus_named_local(self):
        (self.root / "engram.toml").write_text(
            f'[corpora.{LOCAL_CORPUS}]\npath = "{self.root}/x"\n'
        )
        with self.assertRaises(ValueError):
            load_config(self.root)


if __name__ == "__main__":
    unittest.main()
