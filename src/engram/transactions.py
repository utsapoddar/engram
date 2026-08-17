from __future__ import annotations

import json
import os
from pathlib import Path

from .io import atomic_write, repository_lock

JOURNAL_NAME = "correction-journal.json"


def journal_path(root: Path) -> Path:
    return Path(root) / "state" / JOURNAL_NAME


def correction_record(root: Path, old_path: Path, new_path: Path, old_markdown: str,
                      new_markdown: str, old_id: str, new_id: str) -> str:
    root = Path(root)
    return json.dumps({
        "version": 1,
        "old": {"id": old_id, "path": str(old_path.relative_to(root)),
                "target_status": "superseded", "markdown": old_markdown},
        "new": {"id": new_id, "path": str(new_path.relative_to(root)),
                "target_status": "confirmed", "markdown": new_markdown},
    }, sort_keys=True)


def _target(root: Path, relative: str) -> Path:
    root = root.resolve()
    target = (root / relative).resolve()
    if target != root and root not in target.parents:
        raise ValueError("correction journal path escapes repository")
    return target


def _clear(path: Path):
    path.unlink(missing_ok=True)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def recover_correction_unlocked(root: Path) -> bool:
    root = Path(root)
    path = journal_path(root)
    if not path.exists():
        return False
    record = json.loads(path.read_text())
    if record.get("version") != 1:
        raise ValueError("unsupported correction journal")
    # Replacement first preserves confirmed truth through repeated recovery.
    atomic_write(_target(root, record["new"]["path"]), record["new"]["markdown"])
    atomic_write(_target(root, record["old"]["path"]), record["old"]["markdown"])
    _clear(path)
    return True


def recover_correction(root: Path) -> bool:
    with repository_lock(root):
        return recover_correction_unlocked(root)


def clear_correction_journal(root: Path):
    _clear(journal_path(root))
