#!/bin/zsh
# run-debrief.sh <transcript.md>
# runs the 3-skill debrief chain headlessly and notifies on completion. engines are tried
# in order until one writes the report: claude (opus 5.5) first, codex as the backup.
# safe to run by hand: ./run-debrief.sh /path/to/transcript.md
set -euo pipefail

CLAUDE="/Users/rami/.local/bin/claude"
CODEX="/opt/homebrew/bin/codex"
LIFE_OS="/Users/rami/Documents/life-os"
VAULT="/Users/rami/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
TRANSCRIPTS_ROOT="/Users/rami/Documents/transcriptions"
PROMPT_FILE="${0:A:h}/debrief-prompt.md"
PRESENTING_CHECK="${0:A:h}/presenting-check.sh"
NOTIFIER="/opt/homebrew/bin/terminal-notifier"
CLAUDE_MODEL="${DEBRIEF_MODEL:-claude-opus-5-5}"
CODEX_MODEL="${DEBRIEF_CODEX_MODEL:-}"           # empty = codex's configured default
ENGINES=(${=DEBRIEF_ENGINES:-claude codex})      # e.g. DEBRIEF_ENGINES=codex to test the backup alone
RETRY="${0:A:h}/retry-debrief.sh"

# the watcher tells us which attempt this is; run by hand both default to 1,
# so a manual failure goes straight to the loud, reason-bearing alert.
ATTEMPT="${OPENOATS_ATTEMPT:-1}"
MAX_ATTEMPTS="${OPENOATS_MAX_ATTEMPTS:-1}"

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

# one headless run of the debrief prompt; all output goes to the run log
run_engine() {
  case "$1" in
    claude)
      "$CLAUDE" -p "$PROMPT" --dangerously-skip-permissions --model "$CLAUDE_MODEL" \
        --add-dir "$VAULT" --add-dir "$TRANSCRIPTS_ROOT" ;;
    codex)
      # codex has no per-dir grants in this mode; full access matches claude's skip-permissions
      local model_args=(); [[ -n "$CODEX_MODEL" ]] && model_args=(-m "$CODEX_MODEL")
      "$CODEX" exec --dangerously-bypass-approvals-and-sandbox --skip-git-repo-check -C "$LIFE_OS" \
        "${model_args[@]}" "$PROMPT" ;;
    *) echo "unknown engine: $1"; return 2 ;;
  esac >> "$RUN_LOG" 2>&1 < /dev/null
}
engine_model() { [[ $1 == claude ]] && print -r -- "$CLAUDE_MODEL" || print -r -- "${CODEX_MODEL:-default}" }
# success needs a report written by THIS run, not one left over from an earlier attempt
report_written_since() { [[ -f "$REPORT" ]] && (( $(stat -f %m "$REPORT") >= $1 )) }

echo "[$(date)] starting debrief: $NAME (engines: ${ENGINES[*]})" | tee -a "$RUN_LOG"

cd "$LIFE_OS"
STATUS=1; ENGINE=""
for engine in "${ENGINES[@]}"; do
  echo "[$(date)] engine: $engine (model=$(engine_model $engine))" | tee -a "$RUN_LOG"
  started=$(date +%s)
  set +e
  run_engine "$engine"
  STATUS=$?
  set -e
  if (( STATUS == 0 )) && report_written_since $started; then
    ENGINE=$engine
    break
  fi
  echo "[$(date)] $engine failed (status=$STATUS, report=$(report_written_since $started && echo written || echo missing))" | tee -a "$RUN_LOG"
done

# decide notification style once: presenting (screen shared AND mic in use) => quiet banner only, no sticky modal
if "$PRESENTING_CHECK" 2>/dev/null; then PRESENTING=1; else PRESENTING=0; fi

if [[ -z "$ENGINE" ]]; then
  echo "[$(date)] FAILED (all engines: ${ENGINES[*]}, last status=$STATUS, attempt=$ATTEMPT/$MAX_ATTEMPTS)" | tee -a "$RUN_LOG"

  if (( ATTEMPT < MAX_ATTEMPTS )); then
    # not the last attempt: log only, no notification of any kind.
    # the watcher retries on its next tick; the user only hears about it if all attempts fail.
    exit $(( STATUS ? STATUS : 1 ))
  fi

  # final attempt: pull the last real error line out of the log so the alert says WHY,
  # then notify loudly ONCE. the watcher quarantines this file - nothing runs again until
  # retry-debrief.sh clears it, which is exactly what the notification click/buttons do.
  REASON=""
  for line in "${(f)$(<"$RUN_LOG")}"; do
    [[ -n "${line// /}" && "$line" != \[* ]] && REASON="$line"
  done
  REASON=$(print -r -- "$REASON" | LC_ALL=C tr -d '"\\`$')
  REASON="${REASON[1,220]}"
  [[ -n "$REASON" ]] || REASON="no error output captured - open the log"

  # the banner stays in notification center until dismissed, so tapping it hours later still retries
  [[ -x "$NOTIFIER" ]] && "$NOTIFIER" -title "Call debrief gave up ($ATTEMPT attempts) - tap to retry" \
    -subtitle "$NAME" -message "$REASON" -sound Basso -ignoreDnD -execute "'$RETRY' '$NAME'"
  if [[ $PRESENTING -eq 0 ]]; then
    nohup osascript \
      -e "set r to button returned of (display alert \"Call debrief gave up after $ATTEMPT attempts\" message \"$NAME\n\nreason: $REASON\n\nauto-retries are paused for this call. retry whenever you want: the Retry button here, the banner in Notification Center, or retry-debrief.sh\" as critical buttons {\"Dismiss\", \"Open log\", \"Retry now\"} default button \"Retry now\" giving up after 14400)" \
      -e "if r is \"Open log\" then do shell script \"open \" & quoted form of \"$RUN_LOG\"" \
      -e "if r is \"Retry now\" then do shell script \"'$RETRY' '$NAME'\"" \
      >/dev/null 2>&1 &
    disown 2>/dev/null || true
  fi
  exit $(( STATUS ? STATUS : 1 ))
fi

echo "[$(date)] done via $ENGINE -> $REPORT" | tee -a "$RUN_LOG"
MESSAGE="Tap to read the debrief"
[[ "$ENGINE" != "${ENGINES[1]}" ]] && MESSAGE="$MESSAGE (written by the $ENGINE backup)"
# 1) audible banner + Notification Center record, shown even during Focus/Do Not Disturb
[[ -x "$NOTIFIER" ]] && "$NOTIFIER" -title "Call debrief ready" -subtitle "$NAME" \
  -message "$MESSAGE" -sound Hero -ignoreDnD -execute "open '$REPORT'"
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
