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
PRESENTING_CHECK="${0:A:h}/presenting-check.sh"
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

# decide notification style once: presenting (screen shared AND mic in use) => quiet banner only, no sticky modal
if "$PRESENTING_CHECK" 2>/dev/null; then PRESENTING=1; else PRESENTING=0; fi

if [[ $STATUS -ne 0 || ! -f "$REPORT" ]]; then
  echo "[$(date)] FAILED (status=$STATUS, report=$([[ -f $REPORT ]] && echo present || echo missing))" | tee -a "$RUN_LOG"
  # audible, DnD-piercing banner + a sticky critical alert that opens the log on click
  [[ -x "$NOTIFIER" ]] && "$NOTIFIER" -title "Call debrief FAILED" -subtitle "$NAME" \
    -message "See $RUN_LOG" -sound Basso -ignoreDnD
  if [[ $PRESENTING -eq 0 ]]; then
    nohup osascript \
      -e "set r to button returned of (display alert \"Call debrief FAILED\" message \"$NAME could not be debriefed.\" as critical buttons {\"OK\", \"Open log\"} default button \"OK\" giving up after 14400)" \
      -e "if r is \"Open log\" then do shell script \"open \" & quoted form of \"$RUN_LOG\"" \
      >/dev/null 2>&1 &
    disown 2>/dev/null || true
  fi
  exit "${STATUS:-1}"
fi

echo "[$(date)] done -> $REPORT" | tee -a "$RUN_LOG"
# 1) audible banner + Notification Center record, shown even during Focus/Do Not Disturb
[[ -x "$NOTIFIER" ]] && "$NOTIFIER" -title "Call debrief ready" -subtitle "$NAME" \
  -message "Tap to read the debrief" -sound Hero -ignoreDnD -execute "open '$REPORT'"
# 2) sticky critical alert: stays on screen until you act, opens the report on click.
# detached so it never blocks the pipeline; survives job exit because the plist sets AbandonProcessGroup.
# SUPPRESSED while presenting (screen shared + mic in use) so it never pops over a shared screen - the banner still fired above.
if [[ $PRESENTING -eq 0 ]]; then
  nohup osascript \
    -e "set r to button returned of (display alert \"Call debrief ready\" message \"$NAME\" as critical buttons {\"Later\", \"Open debrief\"} default button \"Open debrief\" giving up after 14400)" \
    -e "if r is \"Open debrief\" then do shell script \"open \" & quoted form of \"$REPORT\"" \
    >/dev/null 2>&1 &
  disown 2>/dev/null || true
else
  echo "[$(date)] presenting (screen share + mic) -> quiet banner only, sticky alert suppressed" | tee -a "$RUN_LOG"
fi
