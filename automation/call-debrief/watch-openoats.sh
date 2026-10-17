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
FAIL_DIR="$STATE_DIR/failures"                     # <file>.count per failing transcript
STABLE_SECONDS="${OPENOATS_STABLE_SECONDS:-60}"   # leave a file alone until it has been quiet this long
MAX_ATTEMPTS="${OPENOATS_MAX_ATTEMPTS:-3}"        # after this many failures, quarantine until retry-debrief.sh

mkdir -p "$STATE_DIR" "$FAIL_DIR"
touch "$STATE"

log() { print -r -- "[$(date '+%Y-%m-%d %H:%M:%S')] $*" }

# single-instance lock: WatchPaths + StartInterval can fire overlapping runs.
# the lock is a directory holding the owner's pid. a killed run (e.g. launchctl bootout
# mid-debrief) never reaches its EXIT trap, so a lock whose owner is gone is stale and
# gets taken over - otherwise every later run would exit quietly forever (jul-oct 2026).
take_lock() { mkdir "$LOCK" 2>/dev/null && print -r -- $$ > "$LOCK/pid" }
if ! take_lock; then
  owner=""; [[ -f "$LOCK/pid" ]] && owner=$(<"$LOCK/pid")
  if [[ -n "$owner" ]]; then
    # alive AND still a watcher (guards against the pid being reused by another process)
    ps -p "$owner" -o args= 2>/dev/null | grep -q watch-openoats && exit 0
  else
    # no pid yet: a run between mkdir and writing its pid, or a pre-pid legacy lock
    lock_mtime=$(stat -f %m "$LOCK" 2>/dev/null) || exit 0
    (( $(date +%s) - lock_mtime < 30 )) && exit 0
  fi
  log "stale lock (pid ${owner:-unknown} is not a running watcher) - taking it over"
  rm -rf "$LOCK"
  take_lock || exit 0   # another run beat us to it
fi
trap 'rm -rf "$LOCK"' EXIT

now=$(date +%s)
for f in "$WATCH_DIR"/*.md(On); do   # newest call first: it is the one you are waiting on
  base="${f:t}"
  grep -qxF "$base" "$STATE" && continue           # already done
  countfile="$FAIL_DIR/$base.count"
  fails=0; [[ -f "$countfile" ]] && fails=$(<"$countfile")
  (( fails >= MAX_ATTEMPTS )) && continue           # gave up; retry-debrief.sh re-arms it
  mtime=$(stat -f %m "$f" 2>/dev/null) || continue  # vanished mid-scan; skip
  (( now - mtime < STABLE_SECONDS )) && continue    # still settling; a later run gets it
  if OPENOATS_ATTEMPT=$((fails + 1)) OPENOATS_MAX_ATTEMPTS="$MAX_ATTEMPTS" "$RUNNER" "$f"; then
    print -r -- "$base" >> "$STATE"
    rm -f "$countfile"
  else
    print -r -- $((fails + 1)) > "$countfile"
  fi
done
