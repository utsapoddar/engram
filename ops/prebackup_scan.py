#!/usr/bin/env python3
"""Reject secrets and obvious PII from staged canonical memory files."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from engram.sanitize import sanitize_text


# Email scanning is deliberately omitted because memory may legitimately record
# contact addresses, making an any-email rule too broad for automated backups.
# Credentials remain covered by SECRET_PATTERNS in engram.sanitize and by
# gitleaks.
#
# Phone matching requires separators or an explicit country code so hashes,
# UUIDs, and other long identifiers are not treated as phone numbers.
PHONE = re.compile(
    r"(?<![\w.+-])"                        # not inside a longer token (hex ids, uuids)
    r"(?:\+\d{1,3}[\s.-]?)?"               # optional country code
    r"(?:\(\d{3}\)\s?|\d{3}[\s.-])"        # area code, separator or parens required
    r"\d{3}[\s.-]\d{4}"                    # local part, separator required
    r"(?![\w-])"
)
INTL_PHONE = re.compile(r"(?<![\w.+-])\+\d[\d\s.-]{8,17}\d(?![\w-])")


def contains_phone(text: str) -> bool:
    return bool(PHONE.search(text) or INTL_PHONE.search(text))


def scan_paths(paths: list[Path]) -> list[Path]:
    failures = []
    for path in paths:
        try:
            text = path.read_text(errors="replace")
            sanitize_text(text, max_chars=max(len(text), 1))
        except (OSError, ValueError):
            failures.append(path)
            continue
        if contains_phone(text):
            failures.append(path)
    return failures


def _scan_blobs(root: Path, names: bytes, object_prefix: str) -> list[Path]:
    failures = []
    for raw_name in names.split(b"\0"):
        if not raw_name:
            continue
        name = raw_name.decode()
        object_name = f"{object_prefix}:{name}"
        exists = subprocess.run(
            ["git", "cat-file", "-e", object_name], cwd=root,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        ).returncode == 0
        if not exists:  # Deleted files have no content to scan.
            continue
        content = subprocess.check_output(["git", "show", object_name], cwd=root)
        path = Path(name)
        try:
            text = content.decode(errors="replace")
            sanitize_text(text, max_chars=max(len(text), 1))
        except ValueError:
            failures.append(path)
            continue
        if contains_phone(text):
            failures.append(path)
    return failures


def scan_staged(root: Path) -> list[Path]:
    names = subprocess.check_output(
        ["git", "diff", "--cached", "--name-only", "-z", "--", "hot.md", "raw", "wiki"],
        cwd=root,
    )
    return _scan_blobs(root, names, "")


def scan_commit(root: Path, commit: str) -> list[Path]:
    names = subprocess.check_output(
        ["git", "diff-tree", "--root", "--no-commit-id", "--name-only", "-r", "-z",
         commit, "--", "hot.md", "raw", "wiki"], cwd=root,
    )
    return _scan_blobs(root, names, commit)


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    if len(sys.argv) == 3 and sys.argv[1] == "--commit":
        failures = scan_commit(root, sys.argv[2])
    elif len(sys.argv) > 1:
        failures = scan_paths([Path(arg) for arg in sys.argv[1:]])
    else:
        failures = scan_staged(root)
    if failures:
        print("engram: backup blocked by secret or PII scan:", file=sys.stderr)
        for path in failures:
            print(f"- {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
