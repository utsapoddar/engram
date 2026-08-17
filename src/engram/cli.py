from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .config import LOCAL_CORPUS, load_config
from .maintenance import maintain_repository, repository_status
from .store import MemoryStore

NOTE_TYPES = ["preference", "decision", "project_state", "environment",
              "pattern", "failure", "fact"]


def parser():
    p = argparse.ArgumentParser(prog="engram")
    p.add_argument("--root", type=Path, default=None,
                   help="canonical store root (default: $ENGRAM_ROOT or cwd)")
    sub = p.add_subparsers(dest="command", required=True)
    r = sub.add_parser("recall"); r.add_argument("query")
    r.add_argument("--corpus", default="all",
                   help=f"'{LOCAL_CORPUS}', 'all', or a name declared in engram.toml")
    r.add_argument("--json", action="store_true")
    m = sub.add_parser("remember"); m.add_argument("--type", choices=NOTE_TYPES, default="fact")
    m.add_argument("--stdin", action="store_true", required=True); m.add_argument("--json", action="store_true")
    c = sub.add_parser("correct"); c.add_argument("id")
    c.add_argument("--stdin", action="store_true", required=True); c.add_argument("--json", action="store_true")
    f = sub.add_parser("forget"); f.add_argument("id")
    f.add_argument("--reason", required=True); f.add_argument("--json", action="store_true")
    cap = sub.add_parser("capture-session"); cap.add_argument("--agent", required=True)
    cap.add_argument("--transcript", type=Path, required=True); cap.add_argument("--json", action="store_true")
    for name in ("maintain", "status"):
        q = sub.add_parser(name); q.add_argument("--json", action="store_true")
    return p


def main(argv=None):
    args = parser().parse_args(argv)
    root, external = load_config(args.root)
    store = MemoryStore(root)
    # External corpora are read-only and are never written by this process.
    for corpus in external:
        store.index.register_corpus(corpus.name, corpus.path,
                                    include_pattern=corpus.include_pattern)
    if args.command == "recall":
        result = store.index.search(args.query, corpus=args.corpus)
    elif args.command == "remember":
        result = store.remember(args.type, sys.stdin.read()).__dict__
    elif args.command == "correct":
        result = store.correct(args.id, sys.stdin.read()).__dict__
    elif args.command == "forget":
        result = store.forget(args.id, args.reason).__dict__
    elif args.command == "capture-session":
        result = store.capture_session(args.agent, args.transcript).__dict__
    elif args.command == "maintain":
        result = maintain_repository(root, store.index)
    else:
        store.index.reconcile()
        result = repository_status(root, store.index)
    print(json.dumps(result, indent=None if getattr(args, "json", False) else 2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
