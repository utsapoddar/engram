import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import tomllib
import unittest


REPO = Path(__file__).resolve().parents[1]
INSTALLER = REPO / "integrations" / "install.py"
SESSION_START = REPO / "integrations" / "hooks" / "session_start.py"
CAPTURE = REPO / "integrations" / "hooks" / "capture_session.py"


class IntegrationInstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)

    def run_installer(self, *extra):
        return subprocess.run(
            [sys.executable, str(INSTALLER), "--home", str(self.home),
             "--repo-root", str(REPO), *extra],
            text=True, capture_output=True, check=False,
        )

    def test_installs_exact_integrations_and_preserves_existing_configuration(self):
        (self.home / ".claude").mkdir()
        (self.home / ".codex").mkdir()
        (self.home / ".claude" / "settings.json").write_text(json.dumps({
            "theme": "fixture-theme",
            "hooks": {"SessionStart": [{"matcher": "startup", "hooks": [
                {"type": "command", "command": "existing-start"}
            ]}]},
        }))
        (self.home / ".codex" / "hooks.json").write_text(json.dumps({
            "version": 1,
            "hooks": {"Stop": [{"hooks": [
                {"type": "command", "command": "existing-stop"}
            ]}]},
        }))
        (self.home / ".codex" / "config.toml").write_text(
            'model = "gpt-test"\n\n[features]\nother = true\nhooks = false\n\n[notice]\nseen = true\n'
        )
        (self.home / "AGENTS.md").write_text(
            "# Existing agents\n"
            "- Keep this unrelated rule untouched during installation.\n"
        )
        (self.home / ".claude" / "CLAUDE.md").write_text("# Existing Claude rules\n")

        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)

        skill = self.home / ".claude" / "skills" / "engram"
        self.assertTrue(skill.is_symlink())
        self.assertEqual(skill.resolve(), (REPO / "integrations" / "skill").resolve())
        codex_skills = self.home / ".codex" / "skills"
        self.assertTrue(codex_skills.is_symlink())
        self.assertEqual(codex_skills.resolve(), (self.home / ".claude" / "skills").resolve())
        cli = self.home / ".local" / "bin" / "engram"
        self.assertTrue(cli.is_symlink())
        self.assertEqual(cli.resolve(), (REPO / ".venv/bin/engram").resolve())

        claude = json.loads((self.home / ".claude" / "settings.json").read_text())
        self.assertEqual(claude["theme"], "fixture-theme")
        commands = self._commands(claude["hooks"])
        self.assertEqual(commands["SessionStart"].count(self._start_command()), 1)
        self.assertEqual(commands["PreCompact"], [self._capture_command("claude")])
        self.assertEqual(commands["SessionEnd"], [self._capture_command("claude")])
        self.assertIn("existing-start", commands["SessionStart"])

        codex = json.loads((self.home / ".codex" / "hooks.json").read_text())
        self.assertEqual(codex["version"], 1)
        self.assertEqual(self._commands(codex["hooks"])["SessionStart"], [self._start_command()])
        self.assertEqual(self._commands(codex["hooks"])["Stop"],
                         ["existing-stop", self._capture_command("codex")])

        config = (self.home / ".codex" / "config.toml").read_text()
        self.assertIn('model = "gpt-test"', config)
        self.assertIn("other = true", config)
        self.assertIn("[notice]\nseen = true", config)
        self.assertEqual(config.count("hooks = true"), 1)
        self.assertNotIn("hooks = false", config)

        for path, prefix in ((self.home / "AGENTS.md", "# Existing agents"),
                             (self.home / ".claude" / "CLAUDE.md", "# Existing Claude rules")):
            text = path.read_text()
            self.assertTrue(text.startswith(prefix))
            self.assertEqual(text.count("BEGIN SHARED_AGENT_MEMORY"), 1)
            self.assertIn("plain `remember this`", text)
            self.assertIn("Route plain `remember this` requests to Engram", text)

        # Pre-existing unrelated rules must survive installation untouched.
        self.assertIn("Keep this unrelated rule untouched",
                      (self.home / "AGENTS.md").read_text())

    def test_repeat_is_idempotent_and_dry_run_changes_nothing(self):
        dry = self.run_installer("--dry-run")
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertEqual(list(self.home.rglob("*")), [])

        self.assertEqual(self.run_installer().returncode, 0)
        before = {p.relative_to(self.home): (p.read_bytes() if p.is_file() else p.readlink())
                  for p in self.home.rglob("*") if p.is_file() or p.is_symlink()}
        self.assertEqual(self.run_installer().returncode, 0)
        after = {p.relative_to(self.home): (p.read_bytes() if p.is_file() else p.readlink())
                 for p in self.home.rglob("*") if p.is_file() or p.is_symlink()}
        self.assertEqual(after, before)
        self.assertFalse(list(self.home.rglob("*.bak.*")))

    def test_corrupt_configs_are_backed_up_and_repaired_without_replacing_unrelated_codex_dir(self):
        (self.home / ".claude").mkdir()
        (self.home / ".codex" / "skills").mkdir(parents=True)
        unrelated = self.home / ".codex" / "skills" / "keep.txt"
        unrelated.write_text("keep")
        (self.home / ".claude" / "settings.json").write_text("{broken")
        (self.home / ".codex" / "hooks.json").write_text("[not-json")

        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(unrelated.read_text(), "keep")
        self.assertTrue((self.home / ".codex" / "skills" / "engram").is_symlink())
        self.assertIn("hooks", json.loads((self.home / ".claude" / "settings.json").read_text()))
        self.assertIn("hooks", json.loads((self.home / ".codex" / "hooks.json").read_text()))
        claude_backups = list((self.home / ".claude").glob("settings.json.bak.*"))
        codex_backups = list((self.home / ".codex").glob("hooks.json.bak.*"))
        self.assertEqual(len(claude_backups), 1)
        self.assertEqual(len(codex_backups), 1)
        self.assertEqual(claude_backups[0].read_text(), "{broken")
        self.assertEqual(codex_backups[0].read_text(), "[not-json")

    def test_toml_feature_edit_preserves_indentation_and_inline_comment(self):
        (self.home / ".codex").mkdir()
        config = self.home / ".codex/config.toml"
        config.write_text("[features]\n  hooks = false # managed locally\nother = true\n")
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("  hooks = true # managed locally\n", config.read_text())

    def test_toml_feature_edit_keeps_eof_and_header_variants_valid(self):
        variants = (
            "[features]",
            "[features]\nother = true",
            "[features] # local flags\nother = true",
            "[ features ]\nother = true",
        )
        for original in variants:
            with self.subTest(original=original), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                (home / ".codex").mkdir()
                config = home / ".codex/config.toml"
                config.write_text(original)
                result = subprocess.run(
                    [sys.executable, str(INSTALLER), "--home", str(home),
                     "--repo-root", str(REPO)],
                    text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                rendered = config.read_text()
                self.assertTrue(rendered.endswith("\n"))
                parsed = tomllib.loads(rendered)
                self.assertIs(parsed["features"]["hooks"], True)
                if "other" in original:
                    self.assertIs(parsed["features"]["other"], True)

    def test_alternate_repo_root_cli_targets_virtualenv_entrypoint(self):
        fake_repo = self.home / "alternate repo"
        (fake_repo / ".venv/bin").mkdir(parents=True)
        (fake_repo / ".venv/bin/engram").write_text("venv entrypoint")
        (fake_repo / "integrations/skill").mkdir(parents=True)
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--home", str(self.home),
             "--repo-root", str(fake_repo)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        cli = self.home / ".local/bin/engram"
        self.assertTrue(cli.is_symlink())
        self.assertEqual(cli.resolve(), (fake_repo / ".venv/bin/engram").resolve())

    def test_preserves_unrelated_cli_symlink(self):
        unrelated_home = self.home / "unrelated-home"
        unrelated = unrelated_home / ".local/bin/engram"
        unrelated.parent.mkdir(parents=True)
        target = unrelated_home / "unrelated-target"
        unrelated.symlink_to(target)
        result = subprocess.run(
            [sys.executable, str(INSTALLER), "--home", str(unrelated_home),
             "--repo-root", str(REPO)], text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(unrelated.readlink(), target)

    def test_toml_feature_edit_supports_dotted_quoted_and_inline_forms(self):
        variants = (
            ('features.hooks = false\nfeatures.other = true\n', True),
            ('features.other = true\n', True),
            ('["features"]\nhooks = false\nother = true\n', True),
            ("['features']\n'hooks' = false\nother = true\n", True),
            ('features = { hooks = false, other = true }\n', True),
            ('features = { other = true }\n', True),
        )
        for original, expected_other in variants:
            with self.subTest(original=original), tempfile.TemporaryDirectory() as tmp:
                home = Path(tmp)
                (home / ".codex").mkdir()
                config = home / ".codex/config.toml"
                config.write_text(original)
                result = subprocess.run(
                    [sys.executable, str(INSTALLER), "--home", str(home),
                     "--repo-root", str(REPO)], text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                parsed = tomllib.loads(config.read_text())
                self.assertIs(parsed["features"]["hooks"], True)
                self.assertIs(parsed["features"]["other"], expected_other)

    def test_skill_documents_vendor_neutral_routing_and_truth_rules(self):
        skill = (REPO / "integrations" / "skill" / "SKILL.md").read_text()
        self.assertIn("name: engram", skill)
        self.assertIn("remember this", skill.lower())
        self.assertIn("prior decisions, preferences, failures, and project history", skill)
        self.assertIn("Only a confirmed local note is truth", skill)
        self.assertIn("Open the full", skill)
        self.assertIn("Ask immediately", skill)
        self.assertIn("pending", skill.lower())
        self.assertNotIn("Use the Claude", skill)
        self.assertNotIn("Use the Codex", skill)

    def test_readme_documents_installation_and_one_time_hook_trust(self):
        readme = (REPO / "README.md").read_text()
        self.assertIn("integrations/install.py", readme)
        self.assertIn("Claude", readme)
        self.assertIn("Codex", readme)
        self.assertGreaterEqual(readme.count("integrations/hooks"), 2)
        self.assertIn("trust", readme.lower())

    @staticmethod
    def _commands(hooks):
        return {event: [hook["command"] for group in groups for hook in group.get("hooks", [])]
                for event, groups in hooks.items()}

    def _start_command(self):
        return f"{REPO / '.venv/bin/python'} {SESSION_START}"

    def _capture_command(self, agent):
        return f"{REPO / '.venv/bin/python'} {CAPTURE} --agent {agent}"


class LifecycleHookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = {**os.environ, "ENGRAM_ROOT": str(self.root),
                    "PYTHONPATH": str(REPO / "src")}

    def run_hook(self, script, payload, *args, env=None):
        return subprocess.run([sys.executable, str(script), *args], input=payload,
                              text=True, capture_output=True, env=env or self.env, check=False)

    def test_session_start_emits_hot_memory_and_retrieval_rules_as_plain_stdout(self):
        hot = "# Hot memory\n- Confirmed decision: retries are capped.\n"
        (self.root / "hot.md").write_text(hot)
        result = self.run_hook(SESSION_START, json.dumps({"hook_event_name": "SessionStart"}))
        self.assertEqual(result.returncode, 0)
        self.assertTrue(result.stdout.startswith(hot))
        self.assertIn("Recall decisions, preferences, failures, and project history", result.stdout)
        self.assertIn("Open the full shared note", result.stdout)
        self.assertNotIn("hookSpecificOutput", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_session_start_safely_noops_without_hot_memory(self):
        result = self.run_hook(SESSION_START, "{}")
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))

    def test_capture_accepts_claude_and_codex_payloads_and_is_idempotent(self):
        transcript = self.root / "session.jsonl"
        transcript.write_text('\n'.join([
            json.dumps({"role": "user", "content": "Choose SQLite"}),
            json.dumps({"role": "assistant", "content": "Decision: use SQLite FTS5"}),
        ]))
        for agent, key in (("claude", "transcript_path"), ("codex", "transcriptPath")):
            payload = json.dumps({key: str(transcript)})
            first = self.run_hook(CAPTURE, payload, "--agent", agent)
            second = self.run_hook(CAPTURE, payload, "--agent", agent)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertEqual(first.stdout + second.stdout, "")
        saved = list((self.root / "raw" / "sessions").glob("*.md"))
        self.assertEqual(len(saved), 2)
        self.assertFalse(any(transcript.read_text() == path.read_text() for path in saved))
        self.assertTrue(all("Decision: use SQLite FTS5" in path.read_text() for path in saved))

    def test_capture_supports_agent_env_and_noops_for_missing_transcript(self):
        env = {**self.env, "ENGRAM_AGENT": "codex"}
        result = self.run_hook(CAPTURE, json.dumps({"hook_event_name": "Stop"}), env=env)
        self.assertEqual((result.returncode, result.stdout, result.stderr), (0, "", ""))
        self.assertFalse((self.root / "raw").exists())

    def test_capture_fails_safe_without_leaking_payload_or_transcript(self):
        secret = "never-print-this-transcript-secret"
        result = self.run_hook(CAPTURE, "not-json-" + secret, "--agent", "claude")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertIn("engram capture hook failed", result.stderr)
        self.assertNotIn(secret, result.stderr)


if __name__ == "__main__":
    unittest.main()
