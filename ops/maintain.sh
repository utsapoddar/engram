#!/bin/bash
set -euo pipefail

ROOT="${ENGRAM_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
cd "$ROOT"
mkdir -p state/logs
"$ROOT/.venv/bin/engram" maintain --json > state/last-maintenance.json
