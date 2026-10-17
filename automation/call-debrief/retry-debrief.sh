#!/bin/zsh
# retry-debrief.sh [transcript-name ...]
# re-arms debriefs that gave up after too many failures. clears the failure counter for
# the given transcript(s) - or for everything quarantined when run with no args - then
# kickstarts the launchd watcher so the retry runs right away, in the agent's own TCC
# context (full disk access belongs to the launchd job, not to whoever clicked a button).
# safe to run any time: from a notification click, or by hand hours later.
set -uo pipefail
setopt null_glob

STATE_DIR="${OPENOATS_STATE_DIR:-$HOME/Library/Application Support/openoats-debrief}"
FAIL_DIR="$STATE_DIR/failures"
LABEL="com.rami.openoats-debrief.watch"
NOTIFIER="/opt/homebrew/bin/terminal-notifier"

cleared=()
if (( $# == 0 )); then
  for c in "$FAIL_DIR"/*.count; do
    cleared+=("${${c:t}%.count}")
    rm -f "$c"
  done
else
  for name in "$@"; do
    base="${name:t}"
    [[ "$base" == *.md ]] || base="$base.md"
    if [[ -f "$FAIL_DIR/$base.count" ]]; then
      rm -f "$FAIL_DIR/$base.count"
      cleared+=("$base")
    else
      echo "not quarantined (nothing to clear): $base"
    fi
  done
fi

if (( ${#cleared} == 0 )); then
  echo "nothing to retry"
  exit 0
fi

echo "re-armed: ${cleared[*]}"

# OPENOATS_NO_KICK=1 lets tests exercise the clearing logic without side effects
if [[ "${OPENOATS_NO_KICK:-0}" != 1 ]]; then
  # confirmation banner so a notification-click retry gives visible feedback
  [[ -x "$NOTIFIER" ]] && "$NOTIFIER" -title "Call debrief retry" \
    -message "re-running: ${cleared[*]}" >/dev/null 2>&1
  if launchctl kickstart "gui/$(id -u)/$LABEL" 2>/dev/null; then
    echo "watcher kicked - retry starting now"
  else
    echo "watcher busy or not loaded - retry runs on its next 2-minute tick"
  fi
fi
