from pathlib import Path
import subprocess
import tempfile
import unittest


REPO = Path(__file__).resolve().parents[1]


class OperationsTests(unittest.TestCase):
    def test_prebackup_scan_rejects_secrets_and_pii_only_in_memory_content(self):
        from ops.prebackup_scan import scan_paths, scan_staged

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            safe = root / "safe.md"
            safe.write_text("A confirmed operational decision without personal data.")
            timestamp = root / "timestamp.md"
            timestamp.write_text('updated_at: "2000-01-01T00:00:00+00:00"')
            email = root / "email.md"
            email.write_text("Contact private.person@example.com")
            phone = root / "phone.md"
            phone.write_text("Call +999 555-010-0200")
            compact_phone = root / "compact-phone.md"
            compact_phone.write_text("phone:0000000000\ntel:99999999999\nCall 0000000000: mobile")
            secret = root / "secret.md"
            secret.write_text("Authorization: Bearer abcdefghijklmnopqrstuvwxyz")
            self.assertEqual(scan_paths([safe]), [])
            self.assertEqual(scan_paths([timestamp]), [])
            self.assertEqual(scan_paths([email]), [])
            self.assertEqual(scan_paths([phone]), [phone])
            self.assertEqual(scan_paths([compact_phone]), [])
            self.assertEqual(scan_paths([secret]), [secret])

            repo = root / "repo"
            (repo / "raw/sessions").mkdir(parents=True)
            subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
            staged = repo / "raw/sessions/staged.md"
            staged.write_text("private.person@example.com")
            subprocess.run(["git", "add", "raw/sessions/staged.md"], cwd=repo, check=True)
            self.assertEqual(scan_staged(repo), [])
            staged.unlink()
            subprocess.run(["git", "add", "-u"], cwd=repo, check=True)
            self.assertEqual(scan_staged(repo), [])

    def test_operations_are_portable_and_do_not_ship_a_personal_scheduler(self):
        backup = (REPO / "ops/backup.sh").read_text()
        notify = (REPO / "ops/notify_backup.py").read_text()
        self.assertIn("command -v gitleaks", backup)
        self.assertNotRegex(backup, r'GITLEAKS="/[^"]+"')
        self.assertIn('os.environ.get("ENGRAM_SMTP_HOST", "")', notify)
        self.assertIn("ENGRAM_SMTP_HOST", notify)
        # launchd is offered for macOS convenience, but must not bake in a
        # personal schedule: hours are parameterised with arbitrary defaults.
        launchd = (REPO / "ops/install_launchd.sh").read_text()
        self.assertIn("MAINTAIN_HOUR:-", launchd)
        self.assertIn("BACKUP_HOUR:-", launchd)
        for name in ("backup", "maintain"):
            template = (REPO / f"ops/launchd/dev.engram.{name}.plist.template").read_text()
            self.assertIn("${ENGRAM_ROOT}", template)
            self.assertNotRegex(template, r"<integer>\d+</integer>")

        schedule_path = REPO / "ops/schedule.crontab.example"
        self.assertTrue(schedule_path.is_file())
        schedule = schedule_path.read_text()
        self.assertIn("<maintenance-minute> <maintenance-hour>", schedule)
        self.assertIn("<backup-minute> <backup-hour>", schedule)
        self.assertIn("<store-root>", schedule)
        self.assertIn("<repo-root>/ops/maintain.sh", schedule)
        self.assertIn("<repo-root>/ops/backup.sh", schedule)

    def test_backup_script_scans_staged_memory_without_assuming_a_schedule(self):
        script = (REPO / "ops/backup.sh").read_text()
        self.assertIn("gitleaks git --staged", script.replace('"$GITLEAKS"', "gitleaks"))
        self.assertIn("prebackup_scan.py", script)
        self.assertIn("backup.lock", script)
        self.assertIn("memory backup $STAMP", script)
        # At most one backup per day, enforced by git history rather than by
        # disposable state, with an explicit override.
        self.assertIn('--since="$TODAY 00:00"', script)
        self.assertIn("ENGRAM_BACKUP_ALWAYS", script)
        self.assertIn("refusing to push non-backup commits", script)
        self.assertIn("memory backup", script)
        self.assertNotIn("--allow-empty", script)
        self.assertNotIn("git add -- hot.md raw wiki BACKUP", script)

    def test_backup_recovery_validates_subject_paths_and_uses_crash_safe_lock(self):
        script = (REPO / "ops/backup.sh").read_text()
        self.assertIn('mkdir "$LOCK"', script)
        self.assertIn("git diff-tree --root --no-commit-id --name-only -r", script)
        self.assertIn(r"^memory\ backup\ [0-9]{4}-[0-9]{2}-[0-9]{2}T", script)
        self.assertIn('hot.md|raw/*|wiki/*)', script)
        self.assertNotIn('[ "$subject" = "$backup_subject" ]', script)

if __name__ == "__main__":
    unittest.main()
