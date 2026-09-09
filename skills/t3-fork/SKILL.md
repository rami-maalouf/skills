---
name: t3-fork
description: Fork, branch, or duplicate a T3 Code conversation into a new thread that keeps the full context. Use when the user says "fork this conversation", "branch this chat", "duplicate this thread", "copy this conversation to a new thread", or wants to try a different direction without losing the current one. Also handles branching from an earlier point ("fork from turn 3").
---

# t3-fork

Creates a new T3 Code thread whose Claude Code session is a copy of an existing conversation. The new thread starts with the full prior context. Optionally cut the copy after the n-th user turn to branch from an earlier point.

## How it works

1. Reads the Claude session id behind a T3 thread from `~/.t3/userdata/state.sqlite` (read only).
2. Copies the transcript `~/.claude/projects/<slug>/<session>.jsonl` to a new session id. Subagent transcripts are copied too.
3. Registers the copy through T3's own transcript importer (`agentSessions.import` over the local WebSocket RPC), so the conversation history is visible in the new thread. The importer is all-or-nothing per project, so the script shields every other Claude and Codex transcript of the project with temporary runtime bindings during the call and removes them right after. The first message in the new thread resumes the copied session.

T3 Code must be running. Requires `bun`.

## Commands

Script: `scripts/fork.ts` next to this file. Run it with `bun run`.

```bash
# fork the conversation this agent is running inside
bun run <skill-dir>/scripts/fork.ts --current

# see the user turns first, then branch after turn 3
bun run <skill-dir>/scripts/fork.ts --current --list
bun run <skill-dir>/scripts/fork.ts --current --up-to 3 --title "alt approach"

# fork another thread or a plain claude cli session
bun run <skill-dir>/scripts/fork.ts --thread <t3-thread-id>
bun run <skill-dir>/scripts/fork.ts --session <claude-session-uuid>

# only copy the transcript, do not create a t3 thread
bun run <skill-dir>/scripts/fork.ts --current --no-register

# preview without writing anything
bun run <skill-dir>/scripts/fork.ts --current --dry-run
```

## Agent workflow

1. If the user wants to branch from an earlier point, run `--list` and show the turns. Ask which turn to cut after if unclear.
2. Run the fork with `--current` (default) unless the user names another thread.
3. Report the new thread title and tell the user it is in the T3 sidebar with its history.

## Limits

- The new thread shows user and assistant text only (no tool calls), capped by T3 at 200 messages. The importer marks it settled; the script unsettles it so it appears with active threads. Its id is `import:claudeAgent:<session>`, runtime mode is full-access, and the model comes from the transcript.
- The shield relies on T3 importer internals (it skips transcripts whose runtime binding has a foreign provider instance). A safety net deletes any thread the importer still creates besides the copy. If T3 changes the importer, check the server log for "Could not import an agent session" warnings, which are expected during a fork.
- macOS only: it runs the T3 server CLI from `/Applications/T3 Code*.app` to issue a short-lived bearer token.
