#!/bin/bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRATCH=$(mktemp -d "${TMPDIR:-/tmp}/engram-demo.XXXXXX")
trap 'rm -rf "$SCRATCH"' EXIT
ENGRAM=(python3.12 -m engram --root "$SCRATCH")
export PYTHONPATH="$ROOT/src"

mkdir -p "$SCRATCH/wiki"

echo "== 1. Seed the store with the Orbit API corpus =="
for dir in preferences decisions project_states environments patterns failures facts; do
  mkdir -p "$SCRATCH/wiki/$dir"
done
cp "$ROOT"/demo/seed/*.md "$SCRATCH/wiki/facts/" 2>/dev/null || true
"${ENGRAM[@]}" status >/dev/null

echo
echo "== 2. Remember a new decision =="
NOTE=$(printf 'Orbit API rate limits anonymous clients to 60 requests per minute.' \
  | "${ENGRAM[@]}" remember --type decision --stdin --json)
echo "$NOTE"
ID=$(printf '%s' "$NOTE" | python3.12 -c 'import json,sys; print(json.load(sys.stdin)["id"])')

echo
echo "== 3. Recall it =="
"${ENGRAM[@]}" recall 'rate limit anonymous clients'

echo
echo "== 4. Correct it — the old note is superseded, not overwritten =="
printf 'Orbit API rate limits anonymous clients to 120 requests per minute.' \
  | "${ENGRAM[@]}" correct "$ID" --stdin

echo
echo "== 5. The superseded note still exists on disk =="
grep -rl 'status: "superseded"' "$SCRATCH/wiki" | head -1
grep -h 'status:' $(grep -rl 'status: "superseded"' "$SCRATCH/wiki" | head -1)

echo
echo "== 6. Recall returns only the canonical note =="
"${ENGRAM[@]}" recall 'rate limit anonymous clients'

echo
echo "== 7. Store status =="
"${ENGRAM[@]}" status
