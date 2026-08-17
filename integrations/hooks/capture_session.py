#!/usr/bin/env python3
"""Capture a lifecycle transcript without copying or printing it."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--agent")
    return parser


def _transcript_path(payload: dict) -> str | None:
    for key in ("transcript_path", "transcriptPath"):
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("lifecycle payload must be an object")
        transcript_value = _transcript_path(payload)
        if not transcript_value:
            return 0
        transcript = Path(transcript_value)
        if not transcript.is_file():
            return 0
        agent = args.agent or os.environ.get("ENGRAM_AGENT") or payload.get("agent")
        if agent not in {"claude", "codex"}:
            raise ValueError("agent must be claude or codex")

        repo = Path(__file__).resolve().parents[2]
        sys.path.insert(0, str(repo / "src"))
        from engram.store import MemoryStore

        root = Path(os.environ.get("ENGRAM_ROOT", repo)).expanduser()
        MemoryStore(root).capture_session(agent, transcript)
    except (SystemExit, Exception) as exc:
        if isinstance(exc, KeyboardInterrupt):
            raise
        print(f"engram capture hook failed ({type(exc).__name__})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
