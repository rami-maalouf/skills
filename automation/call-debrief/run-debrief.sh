#!/bin/zsh
# run-debrief.sh <transcript.md>
# runs the 3-skill debrief chain headlessly via `claude -p` and notifies on completion.
# safe to run by hand: ./run-debrief.sh /path/to/transcript.md
set -euo pipefail

CLAUDE="/Users/rami/.local/bin/claude"
LIFE_OS="/Users/rami/Documents/life-os"
VAULT="/Users/rami/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
TRANSCRIPTS_ROOT="/Users/rami/Documents/transcriptions"
PROMPT_FILE="${0:A:h}/debrief-prompt.md"
NOTIFIER="/opt/homebrew/bin/terminal-notifier"
MODEL="${DEBRIEF_MODEL:-}"   # empty = use configured default; set DEBRIEF_MODEL=opus for richer reads

LOG_DIR="$HOME/Library/Logs/OpenOatsDebrief"
mkdir -p "$LOG_DIR"

TRANSCRIPT="${1:?usage: run-debrief.sh <transcript.md>}"
[[ -f "$TRANSCRIPT" ]] || { echo "no such file: $TRANSCRIPT" >&2; exit 1; }

NAME="${TRANSCRIPT:t:r}"
DEBRIEF_DIR="${TRANSCRIPT:h}/debriefs"
REPORT="$DEBRIEF_DIR/$NAME.md"
RUN_LOG="$LOG_DIR/$NAME.log"
mkdir -p "$DEBRIEF_DIR"

# substitute the transcript path into the prompt template (| delimiter; paths have no |)
PROMPT="$(sed "s|{{TRANSCRIPT}}|$TRANSCRIPT|g" "$PROMPT_FILE")"

echo "[$(date)] starting debrief: $NAME (model=${MODEL:-default})" | tee -a "$RUN_LOG"

cd "$LIFE_OS"
ARGS=(-p "$PROMPT" --dangerously-skip-permissions --add-dir "$VAULT" --add-dir "$TRANSCRIPTS_ROOT")
[[ -n "$MODEL" ]] && ARGS+=(--model "$MODEL")

set +e
"$CLAUDE" "${ARGS[@]}" >> "$RUN_LOG" 2>&1
STATUS=$?
set -e

if [[ $STATUS -ne 0 || ! -f "$REPORT" ]]; then
  echo "[$(date)] FAILED (status=$STATUS, report=$([[ -f $REPORT ]] && echo present || echo missing))" | tee -a "$RUN_LOG"
  [[ -x "$NOTIFIER" ]] && "$NOTIFIER" -title "Call debrief failed" -subtitle "$NAME" \
    -message "See $RUN_LOG" -sound Basso
  exit "${STATUS:-1}"
fi

echo "[$(date)] done -> $REPORT" | tee -a "$RUN_LOG"
if [[ -x "$NOTIFIER" ]]; then
  "$NOTIFIER" -title "Call debrief ready" -subtitle "$NAME" \
    -message "Tap to read the debrief" -sound default -execute "open '$REPORT'"
else
  /usr/bin/osascript -e "display notification \"$NAME\" with title \"Call debrief ready\" sound name \"default\""
fi
