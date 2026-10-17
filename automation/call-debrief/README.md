# call-debrief pipeline

an always-on loop that watches for new call transcripts and turns each one into a single, honest debrief - relationship reads per person, communication coaching, and a strategy pressure-test - then pings you to go read it.

## what happens, end to end

1. you finish a call. OpenOats drops a transcript into `~/Documents/transcriptions/OpenOats/`.
2. a `launchd` agent notices (immediately via WatchPaths, and every 2 min as a fallback) and runs `watch-openoats.sh`. a new file is left alone until it has been quiet for 60s (so a half-written transcript is never processed), then picked up on the next tick - so a debrief typically starts within ~1-3 min of the call ending.
3. for each new, finished file (newest call first), `run-debrief.sh` runs the chain headless on **Claude Opus 5.5** (`claude -p`). if claude fails or writes no report (session limit, outage), the same prompt runs on **Codex** (`codex exec`) as a backup, and the banner says the backup wrote it. the chain runs three skills and synthesizes one report:
   - **relationship-debrief** (backbone): who was on the call, a per-person read, how you showed up, and what to do better with each person next time.
   - **communication-analysis**: detailed coaching on your own delivery (run on your de-echoed turns).
   - **co-ceo**: a pressure-test of the decisions and plans discussed.
4. the report is written to `~/Documents/transcriptions/OpenOats/debriefs/<call>.md`.
5. if both engines fail, the run is retried silently on the next tick, up to **3 attempts total**. after the 3rd failure the file is **quarantined** - the watcher stops touching it - and you get ONE loud alert that includes the actual error line from the log, with a **Retry now** button. the matching banner stays in Notification Center until dismissed, so tapping it hours later also retries. you can also re-arm from a terminal any time:

   ```bash
   # one call (name with or without .md), or no args = everything quarantined
   ~/.mac-automations/openoats-debrief/retry-debrief.sh [<call-name>]
   ```

   a retry gets a fresh budget of 3 attempts. the retry goes through `launchctl kickstart`, so it runs in the launchd agent's own Full-Disk-Access context regardless of who clicked.
6. you're alerted two ways: an audible banner (pierces Focus/Do Not Disturb) and a **sticky critical alert that stays on screen until you act** - click "Open debrief" to open the report. (macOS has no scriptable "priority level" beyond this; true Time Sensitive/Critical alerts need Apple entitlements a shell tool can't have. The critical modal alert is the max, and it survives because the launchd plist sets `AbandonProcessGroup`.)
   - **while presenting**, the sticky modal is suppressed and you get only the quiet banner - so nothing pops over a shared screen. `presenting-check.sh` decides this by checking whether one of your meeting apps is **actively using the mic right now** (Zoom, Zen/Google Meet, Slack huddle, Screen Studio, OpenOats) - a far more reliable signal than "screen is shared" (macOS won't expose that) or "app is open" (Zen is always open) or "mic busy" (system/streaming apps hold the mic when you're not on a call). It uses the CoreAudio per-process input API, so an app only counts when it's genuinely in a call. For anything not covered, `touch ~/.openoats-presenting` forces quiet mode (delete when done).

## requirements (macOS Full Disk Access)

A background launchd agent on macOS cannot read file contents under `~/Documents` or touch the iCloud vault without **Full Disk Access**, and cannot even open a script that lives under `~/Documents`. So:

- the runtime scripts are **copied** (not symlinked) to `~/.mac-automations/openoats-debrief/`, out of the protected folder.
- you must grant Full Disk Access to `/bin/zsh` once: System Settings > Privacy & Security > Full Disk Access > + > Cmd+Shift+G > `/bin/zsh` > Open, toggle ON. `/bin/zsh` is chosen because it is a stable path and the agent's actual process (the `claude` binary, whose path changes each update, inherits access as a child).

Without this, the agent runs but can see only filenames - every debrief fails to read the transcript.

## install / uninstall

```bash
# install and start watching (safe: it seeds the current backlog as already-done)
zsh ai-agents-config/automation/call-debrief/install.sh

# stop watching
launchctl bootout gui/$(id -u)/com.rami.openoats-debrief.watch
```

The scripts live in this repo (source of truth). `install.sh` **copies** them to `~/.mac-automations/openoats-debrief/` and registers the launchd agent, matching your existing `com.rami.*` automations. **Because the runtime is a copy, re-run `install.sh` after editing any script or `debrief-prompt.md`** - editing the repo copy alone does not affect the running agent.

## tests

```bash
# unit-tests the watcher logic (new-file detection, freshness skip, dedup, retry, quarantine, re-arm, lock) in a
# sandbox with a stub runner - no claude calls, no real dirs. exits non-zero on any failure.
zsh ai-agents-config/automation/call-debrief/test-watcher.sh
```

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

- **model**: claude runs `claude-opus-5-5` (override with `DEBRIEF_MODEL`). codex runs its configured default from `~/.codex/config.toml` (override with `DEBRIEF_CODEX_MODEL`).
- **engines**: `DEBRIEF_ENGINES` (default `claude codex`) is the order engines are tried in. `DEBRIEF_ENGINES=codex` runs the backup alone; `DEBRIEF_MODEL=bogus-model` makes claude fail fast so you can watch the fallback end to end.
- **responsiveness**: `StartInterval` (in `install.sh`'s plist, default 120s) is the fallback poll cadence; `OPENOATS_STABLE_SECONDS` (default 60) is how long a file must be quiet before processing. Re-run `install.sh` after changing the interval.
- **prompt / chain**: edit `debrief-prompt.md` to change what runs, then re-run `install.sh` to sync it to the runtime copy.

## files

| file | role |
|---|---|
| `debrief-prompt.md` | the orchestration prompt the headless run follows |
| `run-debrief.sh` | runs the chain on one transcript, then notifies |
| `watch-openoats.sh` | finds new+finished transcripts, calls the runner, tracks state + failure counts (paths overridable via `OPENOATS_*` env for testing) |
| `retry-debrief.sh` | re-arms quarantined (3x-failed) debriefs and kickstarts the watcher; wired to the failure notification's click/buttons |
| `apply-proposals.sh` + `apply-proposals-prompt.md` | applies a report's per-person CRM proposals (additive; `--dry-run`) |
| `test-watcher.sh` | unit tests for the watcher logic |
| `install.sh` | copies runtime out of ~/Documents, seeds state, installs the launchd agent |

## state & logs

- processed-file ledger: `~/Library/Application Support/openoats-debrief/.processed`
- failure counters: `~/Library/Application Support/openoats-debrief/failures/<call>.md.count` (3 = quarantined; cleared by success or `retry-debrief.sh`)
- logs: `~/Library/Logs/OpenOatsDebrief/` (`watch.*.log`, and `<call>.log` per run)
- to re-debrief a call: delete its line from `.processed`; it is picked up within ~2 min.
- max attempts knob: `OPENOATS_MAX_ATTEMPTS` (default 3; set it in the plist env if you ever want a different budget).

## notes

- runs unattended with `--dangerously-skip-permissions` and `--add-dir` scoped to the vault and the transcriptions folder - required for a headless agent that writes files with no human to approve prompts. the prompt is fixed and the inputs are your own transcripts.
- launchd will not start a second copy of the job while one is running, and the script also holds a lock - so overlapping triggers never double-process. a file that appears mid-run is caught on the next tick after the run finishes.
- the lock (`.lock/pid` in the state dir) records its owner. if that process is gone - a run killed mid-debrief never reaches its cleanup trap - the next tick takes the lock over and logs `stale lock ... taking it over` to `watch.out.log`. before this, one killed run on 2026-07-16 left a lock that made every later run exit silently until 2026-10-16.
- `install.sh` waits for an active debrief to finish before it copies scripts or reloads the agent, so reinstalling never kills a run.
- each run costs tokens (a full transcript through three skills). tune the model or trim the chain in `debrief-prompt.md` if it adds up.
