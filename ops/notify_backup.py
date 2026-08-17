#!/usr/bin/env python3
"""Email the outcome of an Engram backup.

When SMTP is configured, the message contains the run status and includes the
logged reason after a failure.

Configure the SMTP host, sender, recipient, and optional password through
`ENGRAM_SMTP_HOST`, `ENGRAM_SMTP_ADDRESS`, `ENGRAM_NOTIFY_TO`, and
`ENGRAM_SMTP_PASSWORD`.

This script never exits non-zero and never raises. A notification problem must
not be able to fail the backup it is reporting on.
"""

from __future__ import annotations

import argparse
import os
import socket
import smtplib
import subprocess
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_REASON_CHARS = 4000


def _run(args: list[str], cwd: Path | None = None) -> str:
    try:
        out = subprocess.run(
            args, cwd=cwd, capture_output=True, text=True, timeout=20, check=False
        )
        return out.stdout.strip()
    except Exception:
        return ""


def credentials() -> tuple[str, str]:
    """Return the explicitly configured SMTP address and password."""
    return (
        os.environ.get("ENGRAM_SMTP_ADDRESS", "").strip(),
        os.environ.get("ENGRAM_SMTP_PASSWORD", ""),
    )


def _recipient() -> str | None:
    return os.environ.get("ENGRAM_NOTIFY_TO") or None


def repo_facts() -> list[str]:
    """A few lines of context so the mail is worth reading."""
    facts = []
    head = _run(["git", "log", "-1", "--format=%h %s", "--date=short"], cwd=ROOT)
    if head:
        facts.append(f"HEAD:            {head}")

    upstream = _run(
        ["git", "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"],
        cwd=ROOT,
    )
    if upstream:
        ahead = _run(["git", "rev-list", "--count", f"{upstream}..HEAD"], cwd=ROOT)
        facts.append(f"Unpushed:        {ahead or '?'} commit(s) vs {upstream}")

    dirty = _run(["git", "status", "--porcelain", "--untracked-files=all",
                  "--", "hot.md", "raw", "wiki"], cwd=ROOT)
    pending = len([ln for ln in dirty.splitlines() if ln.strip()])
    facts.append(f"Pending memory:  {pending} file(s) not yet committed")

    staged = _run(["git", "diff", "--cached", "--name-only"], cwd=ROOT)
    if staged.strip():
        facts.append(
            "Staged (WEDGE):  " + ", ".join(staged.split()[:6])
            + "  <- backup cannot run until this is cleared"
        )
    return facts


def read_reason(log: Path | None, offset: int, explicit: str) -> str:
    if explicit:
        return explicit.strip()[:MAX_REASON_CHARS]
    if not log or not log.is_file():
        return "(no reason recorded)"
    try:
        with log.open("r", errors="replace") as fh:
            fh.seek(max(0, offset))
            text = fh.read().strip()
    except OSError as exc:
        return f"(could not read {log}: {exc})"
    if not text:
        # Offset-based read came back empty; fall back to the tail.
        try:
            tail = log.read_text(errors="replace").splitlines()[-15:]
            text = "\n".join(tail).strip()
        except OSError:
            text = ""
    return (text or "(no reason recorded)")[:MAX_REASON_CHARS]


def build(status: str, reason: str, detail: str) -> EmailMessage:
    ok = status == "success"
    today = datetime.now().strftime("%Y-%m-%d")
    host = socket.gethostname() or "unknown host"

    msg = EmailMessage()
    msg["Subject"] = (
        f"{'OK' if ok else 'FAILED'}: Engram backup {today}"
    )
    lines = [
        f"Engram backup — {'SUCCEEDED' if ok else 'FAILED'}",
        f"{today}  |  {host}",
        "",
    ]
    if not ok:
        lines += [
            "Reason logged by backup.sh",
            "-" * 46,
            reason,
            "-" * 46,
            "",
            "The backup did not complete; review the reason before relying on the remote copy.",
            "",
        ]
    elif detail:
        lines += [detail, ""]

    facts = repo_facts()
    if facts:
        lines += ["Repository state", *facts, ""]
    lines += [f"Log: {ROOT}/state/logs/backup.err"]
    msg.set_content("\n".join(lines))
    return msg


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", choices=["success", "failure"], required=True)
    ap.add_argument("--reason", default="", help="failure reason (overrides log)")
    ap.add_argument("--err-log", default=str(ROOT / "state/logs/backup.err"))
    ap.add_argument("--err-offset", type=int, default=0)
    ap.add_argument("--detail", default="", help="extra line for success mail")
    ap.add_argument("--print", action="store_true", help="print instead of sending")
    args = ap.parse_args()

    reason = read_reason(Path(args.err_log), args.err_offset, args.reason)
    msg = build(args.status, reason, args.detail)
    recipient = _recipient()

    if args.print:
        print(f"To: {recipient or '(not configured)'}\nSubject: {msg['Subject']}\n")
        print(msg.get_content())
        return 0

    if recipient is None:
        print("ENGRAM_NOTIFY_TO not set — not sending", file=sys.stderr)
        return 0

    address, password = credentials()
    if not address or not password:
        print(
            "notify_backup: no SMTP credentials "
            "(ENGRAM_SMTP_ADDRESS/ENGRAM_SMTP_PASSWORD) — not sending",
            file=sys.stderr,
        )
        return 0

    msg["From"] = f"Engram <{address}>"
    msg["To"] = recipient
    try:
        smtp_host = os.environ.get("ENGRAM_SMTP_HOST", "")
        if not smtp_host:
            print("ENGRAM_SMTP_HOST not set — not sending", file=sys.stderr)
            return 0
        smtp_port = int(os.environ.get("ENGRAM_SMTP_PORT", "465"))
        with smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30) as server:
            server.login(address, password)
            server.send_message(msg)
        print(f"notify_backup: sent '{msg['Subject']}' to {recipient}")
    except Exception as exc:  # never propagate — must not fail the backup
        print(f"notify_backup: send failed: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # belt and braces
        print(f"notify_backup: unexpected error: {exc}", file=sys.stderr)
        raise SystemExit(0)
