#!/bin/zsh
# watch-openoats.sh
# launchd fires this when ~/Documents/transcriptions/OpenOats changes (and every 30 min as a fallback).
# it debriefs any *.md that is new and finished being written, tracking state so nothing runs twice.
set -euo pipefail
setopt null_glob

WATCH_DIR="/Users/rami/Documents/transcriptions/OpenOats"
RUNNER="${0:A:h}/run-debrief.sh"
STATE_DIR="$HOME/Library/Application Support/openoats-debrief"
STATE="$STATE_DIR/.processed"
LOCK="$STATE_DIR/.lock"
STABLE_SECONDS=90   # leave a file alone until it has been quiet this long (still recording / syncing)

mkdir -p "$STATE_DIR"
touch "$STATE"

# single-instance lock: WatchPaths + StartInterval can fire overlapping runs
if ! mkdir "$LOCK" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

now=$(date +%s)
for f in "$WATCH_DIR"/*.md; do
  base="${f:t}"
  grep -qxF "$base" "$STATE" && continue          # already done
  mtime=$(stat -f %m "$f")
  (( now - mtime < STABLE_SECONDS )) && continue   # still settling; a later run gets it
  if "$RUNNER" "$f"; then
    print -r -- "$base" >> "$STATE"
  fi
done
