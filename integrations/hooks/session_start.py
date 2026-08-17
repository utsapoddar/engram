#!/usr/bin/env python3
"""Inject the bounded hot-memory router as plain hook stdout."""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys


RULES = (
    "Retrieval: Recall decisions, preferences, failures, and project history before answering. "
    "Only confirmed shared notes are truth. Open the full shared note, not a search snippet. "
    "Open actions/projects live in warm.md at the memory root — read it when the user asks "
    "what's pending, open, or what to work on.\n"
)


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
    except (json.JSONDecodeError, OSError):
        return 0

    root = Path(os.environ.get("ENGRAM_ROOT", Path(__file__).resolve().parents[2]))
    hot = root / "hot.md"
    if not hot.is_file():
        return 0
    try:
        text = hot.read_text()
    except OSError:
        return 0
    if not text:
        return 0
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.write(RULES)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
