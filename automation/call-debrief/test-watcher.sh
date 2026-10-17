#!/bin/zsh
# test-watcher.sh - unit tests for watch-openoats.sh logic.
# runs the REAL watch script against a temp sandbox with a stub runner (no claude).
set -uo pipefail

SCRIPT="${0:A:h}/watch-openoats.sh"
RETRY_SCRIPT="${0:A:h}/retry-debrief.sh"
PASS=0; FAIL=0
TMP=$(mktemp -d /tmp/openoats-test.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

WD="$TMP/watch"; SD="$TMP/state"; CALLS="$TMP/calls.log"
mkdir -p "$WD" "$SD"
STUB="$TMP/stub-runner.sh"
cat > "$STUB" <<'EOF'
#!/bin/zsh
print -r -- "${1:t} attempt=${OPENOATS_ATTEMPT:-?}/${OPENOATS_MAX_ATTEMPTS:-?}" >> "$CALLS_FILE"
exit "${STUB_EXIT:-0}"
EOF
chmod +x "$STUB"

run_watcher() {  # arg1 = stub exit code (default 0)
  OPENOATS_WATCH_DIR="$WD" OPENOATS_STATE_DIR="$SD" OPENOATS_RUNNER="$STUB" \
  OPENOATS_STABLE_SECONDS=60 CALLS_FILE="$CALLS" STUB_EXIT="${1:-0}" \
  zsh "$SCRIPT"
}
check() { if [[ "$2" == "$3" ]]; then print -r -- "  PASS: $1"; PASS=$((PASS+1)); else print -r -- "  FAIL: $1 (expected [$2], got [$3])"; FAIL=$((FAIL+1)); fi }
calls() { [[ -f "$CALLS" ]] && wc -l < "$CALLS" | tr -d ' ' || echo 0 }
last_call() { [[ -s "$CALLS" ]] && print -r -- "${$(<"$CALLS")##*$'\n'}" || echo none }
recorded() { grep -qxF "$1" "$SD/.processed" 2>/dev/null && echo yes || echo no }
failcount() { [[ -f "$SD/failures/$1.count" ]] && print -r -- "$(<"$SD/failures/$1.count")" || echo none }
run_retry() { OPENOATS_STATE_DIR="$SD" OPENOATS_NO_KICK=1 zsh "$RETRY_SCRIPT" "$@" >/dev/null }
OLD="202601010000"   # a timestamp well in the past = "stable"

print -r -- "1. empty watch dir"
: > "$CALLS"; run_watcher; check "no runner calls" "0" "$(calls)"

print -r -- "2. a stable (finished) file gets processed and recorded"
touch -t $OLD "$WD/stable.md"; : > "$CALLS"; run_watcher
check "runner called once" "1" "$(calls)"; check "recorded in ledger" "yes" "$(recorded stable.md)"

print -r -- "3. a fresh (still-writing) file is skipped"
touch "$WD/fresh.md"; : > "$CALLS"; run_watcher
check "runner NOT called" "0" "$(calls)"; check "not recorded" "no" "$(recorded fresh.md)"

print -r -- "4. once that file is stable, it is processed"
touch -t $OLD "$WD/fresh.md"; : > "$CALLS"; run_watcher
check "runner called once" "1" "$(calls)"; check "now recorded" "yes" "$(recorded fresh.md)"

print -r -- "5. already-processed files are never re-run"
: > "$CALLS"; run_watcher; check "no runner calls" "0" "$(calls)"

print -r -- "6. a failed run is NOT recorded, and retries next time"
touch -t $OLD "$WD/flaky.md"; : > "$CALLS"; run_watcher 1
check "runner called" "1" "$(calls)"; check "NOT recorded after failure" "no" "$(recorded flaky.md)"
check "failure counted" "1" "$(failcount flaky.md)"
: > "$CALLS"; run_watcher 0
check "retried" "1" "$(calls)"; check "recorded after success" "yes" "$(recorded flaky.md)"
check "counter cleared on success" "none" "$(failcount flaky.md)"

print -r -- "7. a held lock prevents any processing (no double-runs)"
touch -t $OLD "$WD/locked.md"; mkdir -p "$SD/.lock"; : > "$CALLS"; run_watcher
check "runner NOT called while locked" "0" "$(calls)"; rmdir "$SD/.lock"
: > "$CALLS"; run_watcher   # drain locked.md so later tests start clean

print -r -- "8. three failures quarantine the file - no fourth attempt"
touch -t $OLD "$WD/broken.md"
: > "$CALLS"; run_watcher 1; check "attempt 1 passed to runner" "broken.md attempt=1/3" "$(last_call)"
: > "$CALLS"; run_watcher 1; check "attempt 2 passed to runner" "broken.md attempt=2/3" "$(last_call)"
: > "$CALLS"; run_watcher 1; check "attempt 3 passed to runner" "broken.md attempt=3/3" "$(last_call)"
check "counter at 3" "3" "$(failcount broken.md)"
: > "$CALLS"; run_watcher 1
check "quarantined: runner NOT called again" "0" "$(calls)"

print -r -- "9. retry-debrief.sh re-arms it (works with or without .md suffix)"
run_retry broken
check "counter cleared" "none" "$(failcount broken.md)"
: > "$CALLS"; run_watcher 0
check "re-ran after retry, fresh attempt 1" "broken.md attempt=1/3" "$(last_call)"
check "recorded after success" "yes" "$(recorded broken.md)"

print -r -- "10. retry-debrief.sh with no args clears ALL quarantined files"
print -r -- 3 > "$SD/failures/a.md.count"; print -r -- 3 > "$SD/failures/b.md.count"
run_retry
check "a re-armed" "none" "$(failcount a.md)"; check "b re-armed" "none" "$(failcount b.md)"

lock_gone() { [[ -e "$SD/.lock" ]] && echo no || echo yes }

print -r -- "11. a normal run releases its lock"
: > "$CALLS"; run_watcher; check "lock removed after run" "yes" "$(lock_gone)"

print -r -- "12. a lock left by a killed run (dead pid) is taken over"
touch -t $OLD "$WD/after-kill.md"
zsh -c 'exit 0' & dead=$!; wait $dead
mkdir -p "$SD/.lock"; print -r -- $dead > "$SD/.lock/pid"; : > "$CALLS"; run_watcher
check "runner called despite stale lock" "1" "$(calls)"; check "recorded" "yes" "$(recorded after-kill.md)"
check "stale lock cleaned up" "yes" "$(lock_gone)"

print -r -- "13. a legacy pid-less lock older than 30s is taken over (the jul-oct 2026 stall)"
touch -t $OLD "$WD/legacy.md"
mkdir -p "$SD/.lock"; touch -t $OLD "$SD/.lock"; : > "$CALLS"; run_watcher
check "runner called" "1" "$(calls)"; check "recorded" "yes" "$(recorded legacy.md)"

print -r -- "14. a pid reused by an unrelated process does not hold the lock"
touch -t $OLD "$WD/reused.md"
mkdir -p "$SD/.lock"; print -r -- $$ > "$SD/.lock/pid"; : > "$CALLS"; run_watcher
check "runner called" "1" "$(calls)"; check "recorded" "yes" "$(recorded reused.md)"

print -r -- "15. a lock held by a live watcher is respected"
touch -t $OLD "$WD/busy.md"
print -r -- 'sleep 30; :' > "$TMP/watch-openoats-live.sh"
zsh "$TMP/watch-openoats-live.sh" & live=$!
mkdir -p "$SD/.lock"; print -r -- $live > "$SD/.lock/pid"; : > "$CALLS"; run_watcher
check "runner NOT called" "0" "$(calls)"; check "lock kept" "no" "$(lock_gone)"
kill $live 2>/dev/null; wait $live 2>/dev/null
: > "$CALLS"; run_watcher; check "processed once the owner is gone" "yes" "$(recorded busy.md)"

print -r -- "16. pending calls run newest first"
touch -t $OLD "$WD/2026-10-01-0900-old.md" "$WD/2026-10-16-1700-new.md"; : > "$CALLS"; run_watcher
check "newest call first" "2026-10-16-1700-new.md attempt=1/3" "$(sed -n 1p "$CALLS")"

print -r -- ""
print -r -- "===== $PASS passed, $FAIL failed ====="
[[ $FAIL -eq 0 ]]
