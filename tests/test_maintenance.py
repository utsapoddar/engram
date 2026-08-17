from datetime import datetime, timedelta, timezone
import os
import time
import unittest

from engram.maintenance import lint_repository, maintain_repository, process_warm_actions, repository_status
from engram.schema import MemoryNote, parse_note
from engram.store import MemoryStore
from tests.helpers import MemoryTestCase


class MaintenanceTests(MemoryTestCase):
    def test_ttl_and_hot_bound(self):
        raw = self.root / "raw" / "sessions"
        raw.mkdir(parents=True, exist_ok=True)
        old = raw / "old.md"
        old.write_text("old")
        age = time.time() - 91 * 86400
        os.utime(old, (age, age))
        for i in range(80):
            self.store.remember("fact", "word " * 50 + str(i))
        report = maintain_repository(self.root, self.store.index)
        self.assertFalse(old.exists())
        self.assertLessEqual(len((self.root / "hot.md").read_text().split()), 800)
        self.assertGreaterEqual(report["expired_raw"], 1)

    def test_warm_actions_sort_by_score_and_promote_deadlines_to_hot(self):
        today = datetime.now(timezone.utc).date()
        soon = (today + timedelta(days=3)).isoformat()
        far = (today + timedelta(days=90)).isoformat()
        overdue = (today - timedelta(days=2)).isoformat()
        (self.root / "warm.md").write_text(
            "# Open Actions (warm memory)\n\nHeader text.\n\n"
            f"- **Low far** (imp 1, due {far}): minor thing.\n\n"
            "- **Standing high** (imp 5): no deadline.\n\n"
            f"- **Mid soon** (imp 3, due {soon}): coming up.\n\n"
            f"- **Overdue task** (imp 4, due {overdue}): late.\n"
        )
        urgent = process_warm_actions(self.root)
        # 60/40 deadline-weighted: overdue imp4 = 92, soon(3d) imp3 = 81, standing imp5 = 40, far(90d) imp1 = 17
        body = (self.root / "warm.md").read_text()
        order = [body.index(t) for t in ("Overdue task", "Mid soon", "Standing high", "Low far")]
        self.assertEqual(order, sorted(order))
        self.assertTrue(body.startswith("# Open Actions"))
        self.assertEqual([title for title, _, _ in urgent], ["Overdue task", "Mid soon"])

        self.store.remember("fact", "background note")
        maintain_repository(self.root, self.store.index)
        hot = (self.root / "hot.md").read_text()
        self.assertIn("[urgent] Overdue task — OVERDUE by 2d", hot)
        self.assertIn(f"[urgent] Mid soon — due {soon} (3d left)", hot)
        self.assertNotIn("Standing high", hot)
        self.assertLessEqual(len(hot.encode("utf-8")), 800)

    def test_maintenance_builds_confirmed_catalog_and_surfaces_pending_count(self):
        confirmed = self.store.remember("decision", "Use the shared canonical memory")
        self.store.remember("fact", "word " * 80)
        self.store.remember("fact", "Needs clarification", status="inferred")
        maintain_repository(self.root, self.store.index)

        catalog = (self.root / "wiki/index.md").read_text()
        self.assertIn(confirmed.id, catalog)
        self.assertIn("Use the shared canonical memory", catalog)
        self.assertNotIn("Needs clarification", catalog)
        self.assertTrue(all(line == line.rstrip() for line in catalog.splitlines()))
        hot = (self.root / "hot.md").read_text()
        self.assertIn("Pending clarification: 1", hot)
        self.assertLessEqual(len(hot.encode("utf-8")), 800)

    def test_hot_uses_conservative_token_estimate(self):
        for i in range(20):
            self.store.remember("fact", "x" * 500 + str(i))
        maintain_repository(self.root, self.store.index)
        text = (self.root / "hot.md").read_text()
        self.assertLessEqual(len(text.encode("utf-8")), 800)

    def test_hot_bound_is_conservative_for_emoji_and_cjk(self):
        for i in range(10):
            self.store.remember("fact", ("🧠記憶" * 100) + str(i))
        maintain_repository(self.root, self.store.index)
        text = (self.root / "hot.md").read_text()
        self.assertLessEqual(len(text.encode("utf-8")), 800)
        self.assertEqual(repository_status(self.root, self.store.index)["hot_budget"]["estimated_tokens"], len(text.encode("utf-8")))

    def test_lint_links_wikilinks_sources_and_note_ids(self):
        target = self.store.remember("fact", "target")
        good = self.store.remember("fact", f"[file]({target.id}.md) [[{target.id}]]", source_refs=[target.id])
        self.assertFalse(any(good.id in failure for failure in lint_repository(self.root)))
        bad = self.store.remember("fact", "[missing](nope.md) [[absent]]", source_refs=["missing/source.md"])
        failures = lint_repository(self.root)
        self.assertTrue(any("nope.md" in f for f in failures))
        self.assertTrue(any("absent" in f for f in failures))
        self.assertTrue(any("missing/source.md" in f for f in failures))

    def test_lint_ignores_wiki_landing_page_without_note_schema(self):
        (self.root / "wiki" / "index.md").write_text("# Wiki landing page\n")
        self.assertEqual(lint_repository(self.root), [])

    def test_source_reference_alone_is_not_treated_as_correction(self):
        source = self.store.remember("fact", "source truth")
        self.store.remember("fact", "derived truth", source_refs=[source.id])
        maintain_repository(self.root, self.store.index)
        self.assertEqual(self.store.get(source.id).status, "confirmed")

    def test_dedupe_prefers_confirmed_regardless_of_file_order(self):
        for prefix in ("a", "z"):
            if prefix == "a":
                inferred = self.store.remember("fact", f"duplicate {prefix}", status="inferred", id=f"{prefix}-inferred")
                confirmed = self.store.remember("fact", f"duplicate {prefix}", status="confirmed", id=f"{prefix}-confirmed")
            else:
                confirmed = self.store.remember("fact", f"duplicate {prefix}", status="confirmed", id=f"{prefix}-confirmed")
                inferred = self.store.remember("fact", f"duplicate {prefix}", status="inferred", id=f"{prefix}-inferred")
            # Reverse path ordering for the second pair.
            if prefix == "z":
                (self.root / "wiki" / "facts" / f"{inferred.id}.md").rename(self.root / "wiki" / "facts" / "00-inferred.md")
                (self.root / "wiki" / "facts" / f"{confirmed.id}.md").rename(self.root / "wiki" / "facts" / "99-confirmed.md")
        maintain_repository(self.root, self.store.index)
        saved = {parse_note(path.read_text()).id: parse_note(path.read_text())
                 for path in (self.root / "wiki" / "facts").glob("*.md")}
        for id_ in ("a-confirmed", "z-confirmed"):
            self.assertEqual(saved[id_].status, "confirmed")

    def test_status_health_integrity_ttl_and_hot_budget(self):
        raw = self.root / "raw" / "sessions" / "expired.md"; raw.write_text("x")
        age = time.time() - 91 * 86400; os.utime(raw, (age, age))
        (self.root / "hot.md").write_text("x" * 3300)
        self.store.index.reconcile()
        status = repository_status(self.root, self.store.index)
        self.assertIn(status["overall"], {"healthy", "stale"})
        self.assertTrue(status["index_integrity"])
        self.assertEqual(status["ttl_pending"], 1)
        self.assertFalse(status["hot_budget"]["within_limit"])

    def test_corrupt_sqlite_self_heals_on_init_and_status(self):
        corrupt_root = self.root / "corrupt-init"
        (corrupt_root / "state").mkdir(parents=True)
        (corrupt_root / "state" / "memory.sqlite3").write_bytes(b"not sqlite")
        healed = MemoryStore(corrupt_root)
        healed.remember("fact", "works after corrupt init")
        self.assertTrue(healed.index.integrity_ok())
        self.assertTrue(list((corrupt_root / "state").glob("memory.sqlite3.corrupt-*")))
        healed.index.db_path.write_bytes(b"broken again")
        status = repository_status(corrupt_root, healed.index)
        self.assertTrue(status["index_integrity"])
        healed.remember("fact", "works after status recovery")

    def test_lint_reports_duplicate_ids_across_type_directories(self):
        note = MemoryNote.new("fact", "one", id="duplicate-id")
        (self.root / "wiki" / "facts" / "one.md").write_text(note.to_markdown())
        other = MemoryNote.new("decision", "two", id="duplicate-id")
        (self.root / "wiki" / "decisions" / "two.md").write_text(other.to_markdown())
        self.assertTrue(any("duplicate id duplicate-id" in failure for failure in lint_repository(self.root)))


if __name__ == "__main__":
    unittest.main()
