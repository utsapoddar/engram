#!/bin/bash
set -euo pipefail

ROOT="${ENGRAM_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STATE="$ROOT/state"
STAMP=$(date -u +%Y-%m-%dT%H:%M:%SZ)
GITLEAKS="${GITLEAKS:-$(command -v gitleaks || true)}"
cd "$ROOT"
mkdir -p "$STATE/logs"

# Report the outcome when notification settings are configured.
PY="$ROOT/.venv/bin/python"
ERRLOG="$STATE/logs/backup.err"
ERR_OFFSET=$(wc -c < "$ERRLOG" 2>/dev/null || echo 0)
LOCK="$STATE/backup.lock"
LOCK_HELD=0
NOTIFY_SKIP=0
BACKUP_DETAIL=""

finish() {
  local rc=$?
  [ "$LOCK_HELD" = "1" ] && rmdir "$LOCK"
  if [ "$NOTIFY_SKIP" != "1" ] && [ -x "$PY" ]; then
    if [ "$rc" -eq 0 ]; then
      "$PY" "$ROOT/ops/notify_backup.py" --status success \
        --detail "$BACKUP_DETAIL" || true
    else
      "$PY" "$ROOT/ops/notify_backup.py" --status failure \
        --err-log "$ERRLOG" --err-offset "$ERR_OFFSET" || true
    fi
  fi
  exit "$rc"
}
trap finish EXIT

[ -n "$GITLEAKS" ] && [ -x "$GITLEAKS" ] || {
  echo "engram: gitleaks not found; install it or set GITLEAKS" >&2
  exit 1
}
mkdir "$LOCK" 2>/dev/null || {
  echo "engram: backup already running" >&2
  NOTIFY_SKIP=1
  exit 0
}
LOCK_HELD=1

TODAY="${STAMP%%T*}"
backup_subject="memory backup $STAMP"

validate_backup_commit() {
  local commit="$1" subject path
  subject=$(git log -1 --format=%s "$commit")
  [[ "$subject" =~ ^memory\ backup\ [0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$ ]] || {
    echo "engram: refusing to push non-backup commits" >&2
    return 1
  }
  while IFS= read -r path; do
    case "$path" in
      hot.md|raw/*|wiki/*) ;;
      *)
        echo "engram: refusing backup commit containing non-memory path: $path" >&2
        return 1
        ;;
    esac
  done < <(git diff-tree --root --no-commit-id --name-only -r "$commit")
  "$ROOT/.venv/bin/python" "$ROOT/ops/prebackup_scan.py" --commit "$commit"
  "$GITLEAKS" git --no-banner --redact --log-opts="$commit^..$commit"
}

recover_backup() {
  local upstream ahead
  upstream=$(git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null || true)
  if [ -n "$upstream" ]; then
    ahead=$(git rev-list --count "$upstream..HEAD")
    [ "$ahead" -gt 0 ] || return 1
    if [ "$ahead" -ne 1 ]; then
      echo "engram: refusing to push non-backup commits" >&2
      exit 1
    fi
  else
    git remote get-url origin >/dev/null 2>&1 || return 1
  fi
  validate_backup_commit HEAD || exit 1
  if [ -n "$upstream" ]; then git push; else git push -u origin HEAD; fi
  return 0
}

# Finish exactly one previously committed memory backup after an interrupted run.
recover_backup || true

# Git history, not disposable state, enforces at most one backup per day. Set
# ENGRAM_BACKUP_ALWAYS=1 to bypass when you want more frequent snapshots.
if [ "${ENGRAM_BACKUP_ALWAYS:-0}" != "1" ] \
  && git log --since="$TODAY 00:00" --format=%s | grep -q "^memory backup $TODAY"; then
  NOTIFY_SKIP=1   # already backed up (and already reported) today
  exit 0
fi

git rev-parse --verify '@{upstream}' >/dev/null 2>&1 || {
  echo "engram: configure an upstream before enabling backup" >&2
  exit 1
}

"$ROOT/ops/maintain.sh"

# Never absorb a developer's staged work into an automated memory commit.
if ! git diff --cached --quiet; then
  echo "engram: backup skipped because unrelated staged changes exist" >&2
  exit 1
fi

git add -- hot.md raw wiki
if git diff --cached --quiet; then
  BACKUP_DETAIL="No new memory to back up — repository already up to date."
  exit 0
fi

# Reset rejected staging so a later run can retry cleanly.
if ! "$ROOT/.venv/bin/python" "$ROOT/ops/prebackup_scan.py" \
  || ! "$GITLEAKS" git --staged --no-banner --redact; then
  git reset --quiet
  echo "engram: scan rejected the staged memory; index reset so the next run can retry" >&2
  exit 1
fi

BACKUP_DETAIL="Committed and pushed $(git diff --cached --name-only | wc -l | tr -d ' ') file(s)."
git commit -m "$backup_subject"
git push
