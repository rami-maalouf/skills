#!/bin/zsh
# test-watcher.sh - unit tests for watch-openoats.sh logic.
# runs the REAL watch script against a temp sandbox with a stub runner (no claude).
set -uo pipefail

SCRIPT="${0:A:h}/watch-openoats.sh"
PASS=0; FAIL=0
TMP=$(mktemp -d /tmp/openoats-test.XXXXXX)
trap 'rm -rf "$TMP"' EXIT

WD="$TMP/watch"; SD="$TMP/state"; CALLS="$TMP/calls.log"
mkdir -p "$WD" "$SD"
STUB="$TMP/stub-runner.sh"
cat > "$STUB" <<'EOF'
#!/bin/zsh
print -r -- "${1:t}" >> "$CALLS_FILE"
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
recorded() { grep -qxF "$1" "$SD/.processed" 2>/dev/null && echo yes || echo no }
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
: > "$CALLS"; run_watcher 0
check "retried" "1" "$(calls)"; check "recorded after success" "yes" "$(recorded flaky.md)"

print -r -- "7. a held lock prevents any processing (no double-runs)"
touch -t $OLD "$WD/locked.md"; mkdir -p "$SD/.lock"; : > "$CALLS"; run_watcher
check "runner NOT called while locked" "0" "$(calls)"; rmdir "$SD/.lock"

print -r -- ""
print -r -- "===== $PASS passed, $FAIL failed ====="
[[ $FAIL -eq 0 ]]
