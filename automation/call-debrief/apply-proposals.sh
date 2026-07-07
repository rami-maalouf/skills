#!/bin/zsh
# apply-proposals.sh <report.md> [--dry-run]
# applies the "Proposed CRM updates" from a debrief report into My Social Circle/ (additive only).
# the #meeting note is already written by the debrief; this only touches person notes.
# --dry-run previews what it would do without writing anything.
set -euo pipefail

CLAUDE="/Users/rami/.local/bin/claude"
LIFE_OS="/Users/rami/Documents/life-os"
VAULT="/Users/rami/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian"
TRANSCRIPTS_ROOT="/Users/rami/Documents/transcriptions"
PROMPT_FILE="${0:A:h}/apply-proposals-prompt.md"
MODEL="${DEBRIEF_MODEL:-}"

REPORT="${1:?usage: apply-proposals.sh <report.md> [--dry-run]}"
[[ -f "$REPORT" ]] || { echo "no such report: $REPORT" >&2; exit 1; }

PROMPT="$(sed "s|{{REPORT}}|$REPORT|g" "$PROMPT_FILE")"
if [[ "${2:-}" == "--dry-run" ]]; then
  PROMPT="$PROMPT

DRY RUN: do not write or create any files. Instead print, file by file, exactly what you WOULD create or add."
fi

cd "$LIFE_OS"
ARGS=(-p "$PROMPT" --dangerously-skip-permissions --add-dir "$VAULT" --add-dir "$TRANSCRIPTS_ROOT")
[[ -n "$MODEL" ]] && ARGS+=(--model "$MODEL")

# output goes to the terminal so Rami sees the CREATED/UPDATED/SKIPPED ledger
"$CLAUDE" "${ARGS[@]}"
