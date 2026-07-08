#!/bin/zsh
# watch-openoats.sh
# launchd fires this when ~/Documents/transcriptions/OpenOats changes, and every 2 min as a
# fallback. it debriefs any *.md that is new and finished being written, tracking state so
# nothing runs twice. paths are overridable via env vars so the logic can be unit-tested.
set -uo pipefail
setopt null_glob

WATCH_DIR="${OPENOATS_WATCH_DIR:-/Users/rami/Documents/transcriptions/OpenOats}"
RUNNER="${OPENOATS_RUNNER:-${0:A:h}/run-debrief.sh}"
STATE_DIR="${OPENOATS_STATE_DIR:-$HOME/Library/Application Support/openoats-debrief}"
STATE="$STATE_DIR/.processed"
LOCK="$STATE_DIR/.lock"
STABLE_SECONDS="${OPENOATS_STABLE_SECONDS:-60}"   # leave a file alone until it has been quiet this long

mkdir -p "$STATE_DIR"
touch "$STATE"

# single-instance lock: WatchPaths + StartInterval can fire overlapping runs.
# the lock is a directory; the EXIT trap removes it even if a run is slow.
if ! mkdir "$LOCK" 2>/dev/null; then
  exit 0
fi
trap 'rmdir "$LOCK" 2>/dev/null' EXIT

now=$(date +%s)
for f in "$WATCH_DIR"/*.md; do
  base="${f:t}"
  grep -qxF "$base" "$STATE" && continue           # already done
  mtime=$(stat -f %m "$f" 2>/dev/null) || continue  # vanished mid-scan; skip
  (( now - mtime < STABLE_SECONDS )) && continue    # still settling; a later run gets it
  if "$RUNNER" "$f"; then
    print -r -- "$base" >> "$STATE"
  fi
done
