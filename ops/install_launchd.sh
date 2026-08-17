#!/bin/bash
# Install the macOS launchd agents for scheduled maintenance and backup.
# On other platforms use ops/schedule.crontab.example instead.
set -euo pipefail

ROOT="${ENGRAM_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
DEST="$HOME/Library/LaunchAgents"
UID_VALUE=$(id -u)

# Arbitrary defaults. Override to whatever suits your machine — there is
# nothing special about these times.
MAINTAIN_HOUR="${MAINTAIN_HOUR:-1}"
MAINTAIN_MINUTE="${MAINTAIN_MINUTE:-0}"
BACKUP_HOUR="${BACKUP_HOUR:-2}"
BACKUP_MINUTE="${BACKUP_MINUTE:-0}"

command -v launchctl >/dev/null 2>&1 || {
  echo "engram: launchctl not found; this installer is macOS-only." >&2
  echo "engram: use ops/schedule.crontab.example on other platforms." >&2
  exit 1
}

mkdir -p "$DEST" "$ROOT/state/logs"

for name in backup maintain; do
  label="dev.engram.$name"
  template="$ROOT/ops/launchd/$label.plist.template"
  target="$DEST/$label.plist"
  [ -f "$template" ] || { echo "engram: missing $template" >&2; exit 1; }
  # sed rather than envsubst: gettext is not part of a stock macOS install.
  sed -e "s|\${ENGRAM_ROOT}|$ROOT|g" \
      -e "s|\${MAINTAIN_HOUR}|$MAINTAIN_HOUR|g" \
      -e "s|\${MAINTAIN_MINUTE}|$MAINTAIN_MINUTE|g" \
      -e "s|\${BACKUP_HOUR}|$BACKUP_HOUR|g" \
      -e "s|\${BACKUP_MINUTE}|$BACKUP_MINUTE|g" \
      "$template" > "$target"
  plutil -lint "$target" >/dev/null
  launchctl bootout "gui/$UID_VALUE/$label" 2>/dev/null || true
  launchctl bootstrap "gui/$UID_VALUE" "$target"
  echo "engram: installed $label"
done
