# call-debrief pipeline

an always-on loop that watches for new call transcripts and turns each one into a single, honest debrief - relationship reads per person, delivery coaching, and a strategy pressure-test - then pings you to go read it.

## what happens, end to end

1. you finish a call. OpenOats drops a transcript into `~/Documents/transcriptions/OpenOats/`.
2. a `launchd` agent notices the new file and runs `watch-openoats.sh`.
3. for each new, finished file, `run-debrief.sh` calls `claude -p` headless, which runs three skills and synthesizes one report:
   - **relationship-debrief** (backbone): who was on the call, a per-person read, how you showed up, and what to do better with each person next time.
   - **communication-analysis**: coaching on your own delivery (run on your de-echoed turns).
   - **co-ceo**: a pressure-test of the decisions and plans discussed.
4. the report is written to `~/Documents/transcriptions/OpenOats/debriefs/<call>.md`.
5. a macOS notification fires - **tap it to open the report**.

## the CRM policy (hybrid)

- the factual `#meeting` note is written into the vault automatically (`My Meetings/<call>.md`) - it is a low-risk log.
- the interpretive per-person observations are left as **proposals inside the report**. nothing is written into `My Social Circle/` until you say so (that folder is gitignored with no undo, so the bar for auto-writing it is high).

## install / uninstall

```bash
# install and start watching (safe: it seeds the current backlog as already-done)
zsh ai-agents-config/automation/call-debrief/install.sh

# stop watching
launchctl bootout gui/$(id -u)/com.rami.openoats-debrief.watch
```

The scripts live in this repo (source of truth). `install.sh` symlinks them to `~/.mac-automations/openoats-debrief/` and registers the launchd agent, matching your existing `com.rami.*` automations.

## run one by hand (no waiting for a call)

```bash
ai-agents-config/automation/call-debrief/run-debrief.sh \
  "/Users/rami/Documents/transcriptions/OpenOats/<some-call>.md"
```

## apply the per-person proposals

The debrief leaves per-person CRM updates as proposals (the `#meeting` note is already written). When you've read a report and want its person-note updates applied to `My Social Circle/`:

```bash
# preview only - writes nothing
ai-agents-config/automation/call-debrief/apply-proposals.sh "<report.md>" --dry-run

# apply (additive only: creates missing notes, appends a dated debrief note +
# a "How to communicate with them" section + #ref/convo tasks; never overwrites)
ai-agents-config/automation/call-debrief/apply-proposals.sh "<report.md>"
```

It prints a CREATED / UPDATED / TASKS ADDED / SKIPPED ledger so you see exactly what changed.

## knobs

- **model**: defaults to your configured Claude Code model. For richer relationship reads on important calls, set `DEBRIEF_MODEL=opus` in the environment before a manual run. Sonnet is fine and cheaper for routine syncs.
- **prompt**: edit `debrief-prompt.md` to change what the chain does or which skills run. No reinstall needed - the runner reads it fresh each time.
- **stability delay**: `watch-openoats.sh` waits `STABLE_SECONDS` (90s) after a file's last change before processing, so it never debriefs a half-written transcript.

## files

| file | role |
|---|---|
| `debrief-prompt.md` | the orchestration prompt the headless run follows |
| `run-debrief.sh` | runs the chain on one transcript, then notifies |
| `watch-openoats.sh` | finds new+finished transcripts, calls the runner, tracks state |
| `install.sh` | symlinks runtime, seeds state, installs the launchd agent |
| `apply-proposals.sh` | applies a report's per-person CRM proposals (additive; has `--dry-run`) |
| `apply-proposals-prompt.md` | the prompt the apply step follows |

## state & logs

- processed-file ledger: `~/Library/Application Support/openoats-debrief/.processed`
- logs: `~/Library/Logs/OpenOatsDebrief/` (`watch.*.log`, and `<call>.log` per run)
- to re-debrief a call: delete its line from `.processed`, then touch/save any file in the watch dir.

## notes

- runs unattended with `--dangerously-skip-permissions` and `--add-dir` scoped to the vault and the transcriptions folder. that is required for a headless agent that writes files without a human to approve prompts; the prompt is fixed and the inputs are your own transcripts. if you would rather run attended, drop that flag and trigger `run-debrief.sh` yourself.
- each run costs tokens (a full transcript through three skills). that is the price of the automation; tune the model or trim the chain in `debrief-prompt.md` if it adds up.
