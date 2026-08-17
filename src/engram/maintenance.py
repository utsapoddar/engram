from __future__ import annotations

from pathlib import Path
import re
import time
from datetime import date, datetime, timezone

from .io import atomic_write, repository_lock
from .schema import parse_note
from .transactions import recover_correction


def lint_repository(root: Path):
    failures = []
    paths = [path for path in (root / "wiki").glob("**/*.md") if path != root / "wiki" / "index.md"]
    note_ids = set()
    id_paths = {}
    for path in paths:
        try:
            note_id = parse_note(path.read_text()).id
            if path.stem != note_id:
                failures.append(f"{path}: filename id mismatch: {path.stem} != {note_id}")
            note_ids.add(note_id)
            id_paths.setdefault(note_id, []).append(path)
        except ValueError:
            pass
    for note_id, duplicates in id_paths.items():
        if len(duplicates) > 1:
            failures.append(f"duplicate id {note_id}: {', '.join(str(path) for path in sorted(duplicates))}")
    def exists(reference, path):
        reference = reference.split("#", 1)[0]
        if not reference or reference in note_ids or reference.startswith(("http://", "https://", "mailto:", "#")):
            return True
        candidates = [path.parent / reference, root / reference]
        if not Path(reference).suffix:
            candidates.extend(path.parent / f"{reference}.md" for _ in [0])
            candidates.extend(root.glob(f"wiki/**/{reference}.md"))
        return any(candidate.exists() for candidate in candidates)
    for path in paths:
        try:
            note = parse_note(path.read_text())
            for ref in note.source_refs:
                if not exists(ref, path):
                    failures.append(f"{path}: broken source {ref}")
            for target in re.findall(r"\[[^]]*\]\(([^)]+)\)", note.body):
                if not exists(target, path):
                    failures.append(f"{path}: broken link {target}")
            for target in re.findall(r"\[\[([^]|]+)(?:\|[^]]+)?\]\]", note.body):
                if not exists(target, path):
                    failures.append(f"{path}: broken wiki link {target}")
        except ValueError as exc:
            failures.append(f"{path}: {exc}")
    return failures


def process_warm_actions(root: Path, today=None, promote_days=14):
    """Sort warm.md entries by descending importance+deadline score; return entries due soon.

    Entry first lines carry optional metadata: `- **Title** (imp N[, due YYYY-MM-DD]): ...`
    imp defaults to 3. Both components are normalized to 0-100 and weighted 60/40:
    score = 0.6*deadline_urgency + 0.4*(imp/5*100), where deadline_urgency is
    overdue 100, <=3d 95, <=7d 85, <=14d 70, <=30d 50, <=60d 30, <=90d 15, else 5;
    no deadline = 0. Entries due within `promote_days` (or overdue) are returned as
    (title, due, days_left) for promotion into hot.md.
    """
    warm = root / "warm.md"
    if not warm.is_file():
        return []
    parts = re.split(r"\n(?=- \*\*)", warm.read_text())
    header, blocks = parts[0], parts[1:]
    if not blocks:
        return []
    today = today or datetime.now(timezone.utc).date()
    scored = []
    for block in blocks:
        first = block.split("\n", 1)[0]
        title_match = re.match(r"- \*\*(.+?)\*\*", first)
        title = title_match.group(1) if title_match else first.lstrip("- ")[:60]
        imp_match = re.search(r"\bimp\s*(\d)\b", first)
        importance = int(imp_match.group(1)) if imp_match else 3
        due_match = re.search(r"\bdue\s*(\d{4}-\d{2}-\d{2})\b", first)
        due, days = None, None
        if due_match:
            due = due_match.group(1)
            days = (date.fromisoformat(due) - today).days
        if days is None:
            urgency = 0
        elif days < 0:
            urgency = 100
        elif days <= 3:
            urgency = 95
        elif days <= 7:
            urgency = 85
        elif days <= 14:
            urgency = 70
        elif days <= 30:
            urgency = 50
        elif days <= 60:
            urgency = 30
        elif days <= 90:
            urgency = 15
        else:
            urgency = 5
        score = 0.6 * urgency + 0.4 * (importance / 5 * 100)
        scored.append((score, days if days is not None else 10 ** 6, title, due, days, block.rstrip()))
    scored.sort(key=lambda item: (-item[0], item[1]))
    atomic_write(warm, header.rstrip() + "\n\n" + "\n\n".join(item[5] for item in scored) + "\n")
    return [(title, due, days) for _, _, title, due, days, _ in scored
            if days is not None and days <= promote_days]


def maintain_repository(root: Path, index, *, ttl_days=90, hot_words=800):
    root = Path(root)
    recover_correction(root)
    cutoff, expired = time.time() - ttl_days * 86400, 0
    with repository_lock(root):
        for path in (root / "raw" / "sessions").glob("*.md"):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                expired += 1
        records, duplicates = [], 0
        for path in (root / "wiki").glob("**/*.md"):
            try:
                note = parse_note(path.read_text())
            except ValueError:
                continue
            records.append((path, note))

        by_id = {note.id: (path, note) for path, note in records}
        # Complete corrections interrupted after the safer replacement-first write.
        for _, replacement in records:
            if replacement.status != "confirmed" or "correction" not in replacement.tags:
                continue
            for source_id in replacement.source_refs:
                linked = by_id.get(source_id)
                if linked and linked[1].status == "confirmed":
                    linked[1].status = "superseded"
                    atomic_write(linked[0], linked[1].to_markdown())

        groups = {}
        for path, note in records:
            normalized = re.sub(r"\s+", " ", note.body.lower()).strip()
            groups.setdefault(normalized, []).append((path, note))
        for group in groups.values():
            if len(group) < 2:
                continue
            ordered = sorted(group, key=lambda item: (
                0 if item[1].status == "confirmed" else 1,
                -datetime.fromisoformat(item[1].updated_at).timestamp(), str(item[0])))
            for path, loser in ordered[1:]:
                if loser.status != "superseded":
                    loser.status = "superseded"
                    atomic_write(path, loser.to_markdown())
                    duplicates += 1
        confirmed_records = [(path, note) for path, note in records if note.status == "confirmed"]
        notes = [note for _, note in confirmed_records]
        notes.sort(key=lambda n: n.updated_at, reverse=True)
        catalog = ["# Memory Index\n\nConfirmed canonical memory.\n\n"]
        for path, note in sorted(confirmed_records, key=lambda item: (item[1].type, item[1].id)):
            relative = path.relative_to(root / "wiki")
            summary = re.sub(r"\s+", " ", note.body).strip()[:160].rstrip()
            catalog.append(f"- [{note.id}]({relative}) — {note.type} — {summary}\n")
        atomic_write(root / "wiki" / "index.md", "".join(catalog))

        pending = sum(1 for _, note in records if note.status in {"inferred", "conflicted"})
        urgent = process_warm_actions(root)
        sections = [
            "# Hot Memory\n\nConfirmed memory only.\n"
            f"Pending clarification: {pending}.\n"
        ]
        for title, due, days in urgent[:5]:
            label = f"OVERDUE by {-days}d" if days < 0 else f"due {due} ({days}d left)"
            sections.append(f"- [urgent] {title} — {label}; details in warm.md\n")
        byte_budget = hot_words
        for note in notes:
            candidate = f"- [{note.type}] {note.body.replace(chr(10), ' ')}\n"
            if len(("".join(sections) + candidate).encode("utf-8")) > byte_budget:
                break
            sections.append(candidate)
        atomic_write(root / "hot.md", "".join(sections))
    index.reconcile()
    lint = lint_repository(root)
    return {"expired_raw": expired, "duplicates": duplicates, "lint_failures": lint}


def repository_status(root: Path, index):
    root = Path(root)
    recover_correction(root)
    lint = lint_repository(root)
    unresolved = 0
    for path in (root / "wiki").glob("**/*.md"):
        try:
            if parse_note(path.read_text()).status in {"inferred", "conflicted"}:
                unresolved += 1
        except ValueError:
            pass
    markers = [str(p) for name in ("BACKUP", ".backup", "backup.marker") if (p := root / name).exists()]
    integrity = index.integrity_ok()
    age = index.age_seconds()
    ttl_cutoff = time.time() - 90 * 86400
    ttl_pending = sum(1 for p in (root / "raw" / "sessions").glob("*.md") if p.stat().st_mtime < ttl_cutoff)
    hot = (root / "hot.md").read_text(errors="replace") if (root / "hot.md").exists() else ""
    hot_tokens = len(hot.encode("utf-8"))
    stale = age is None or age > 86400 or not integrity or bool(lint) or ttl_pending > 0 or hot_tokens > 800
    return {"overall": "stale" if stale else "healthy", "index_age_seconds": age,
            "index_stale_threshold_seconds": 86400, "index_integrity": integrity,
            "embedding_available": index.semantic_available,
            "unresolved_clarification_count": unresolved, "lint_failures": lint,
            "ttl_pending": ttl_pending, "hot_budget": {"estimated_tokens": hot_tokens, "limit": 800,
            "within_limit": hot_tokens <= 800}, "backup_marker": markers[0] if markers else None}
