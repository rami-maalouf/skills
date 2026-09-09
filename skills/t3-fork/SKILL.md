---
name: t3-fork
description: Fork, branch, or duplicate a T3 Code conversation into a new thread that keeps the full context, with an option to keep only the first or last N turns. Manual only, run with /t3-fork; it does not trigger itself.
disable-model-invocation: true
---

# t3-fork

Copies a T3 Code conversation into a new thread, full history included. `--first n` keeps only the first n user turns; `--last n` keeps only the last n, with no memory of anything earlier. Forking `--current` drops the triggering `/t3-fork` turn itself by default.

Reads the session id for a thread from `~/.t3/userdata/state.sqlite` (read only), copies the transcript to a new session id, and registers it through T3's own transcript importer so history shows in the UI. T3 Code must be running. Requires `bun`, macOS only.

## Commands

```bash
bun run <skill-dir>/scripts/fork.ts --current                       # fork this conversation
bun run <skill-dir>/scripts/fork.ts --current --list                # show numbered turns first
bun run <skill-dir>/scripts/fork.ts --current --first 3              # keep turns 1-3
bun run <skill-dir>/scripts/fork.ts --current --last 2               # keep only the last 2 turns
bun run <skill-dir>/scripts/fork.ts --thread <t3-thread-id>          # fork another thread
bun run <skill-dir>/scripts/fork.ts --session <claude-session-uuid>  # fork any claude session
bun run <skill-dir>/scripts/fork.ts --current --no-register          # copy the transcript only
bun run <skill-dir>/scripts/fork.ts --current --dry-run              # preview, change nothing
```

Add `--title "text"` to any of these. `--include-trigger` keeps the `/t3-fork` turn instead of dropping it.

## Workflow

Run `--list` first if the branch point is unclear, then ask the user whether they want `--first` or `--last`. Report the new thread's title and that it is in the T3 sidebar with its history.

## Limits

- Pick one of `--first`/`--last`, not both. The default trigger-drop only applies to `--current` with neither flag given.
- New threads show user/assistant text only, no tool calls, capped by T3 at 200 messages.
- The importer is all-or-nothing per project; the script shields other transcripts during the call and removes the shield right after. If T3 changes the importer, "Could not import an agent session" warnings in the server log are expected during a fork.
