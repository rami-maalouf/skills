---
name: t3-fork
description: Fork a T3 Code conversation into a new thread that keeps its full context, optionally from an earlier turn (--first n) or onto a different agent or model (--provider). Uses T3's own fork command, so the agent gets a real native session fork when it supports one. Manual only, run with /t3-fork; it does not trigger itself.
disable-model-invocation: true
---

# t3-fork

A thin wrapper over T3 Code's own fork command, exposed by the `t3-code` MCP server. There is no script and nothing writes to T3's database, so T3 updates do not break it.

## Arguments

- no arguments: fork this thread at its latest completed turn. The turn that ran `/t3-fork` is still running, so it is not part of the fork.
- `--first n`: fork right after the n-th user turn.
- `--thread <id>`: fork another T3 thread instead of this one.
- `--title "text"`: title of the new thread. Default: `<source title> (fork)`.
- `--provider <instance> [--model <id>]`: move the fork to a different agent or model (for example `codex`, `cursor`, or `claudeAgent` with another model).

## Steps

1. **Source thread.** Use the `--thread` value, or else this thread. When you need this thread's id (for `--first`), read `parentThreadId` from `orchestrator_capabilities`.
2. **Source point.**
   - Default: `{"type": "latest_stable"}`.
   - `--first n`: call `t3_thread_read` on the source with `view: "messages"`, and page with `afterPosition` until `hasMore` is false. Take the n-th item of type `user_message` and use its `runId`: `{"type": "run", "runId": "<runId>"}`. If the source has fewer than n user turns, stop and tell the user.
3. **Fork.** Call `t3_thread_fork` with the source point, `threadId` (omit it for this thread), and the title. Keep the returned `targetThreadId`.
4. **Agent (only with `--provider`).** Call `orchestrator_capabilities` and check that the provider instance exists and has no blocking `constraints`. If `--model` is missing, ask the user which of that provider's models to use. Then call `t3_thread_configure` on the fork with `{"instanceId": "<instance>", "model": "<model>"}`. Do this before anyone sends the fork a message.
5. **Report.** Link the fork as `[title](t3-thread://v1/<targetThreadId>)`, and say which turn it starts from and which agent it uses. Do not send the fork a message unless the user asks.

## How the context carries over

T3 decides this when the fork receives its first message:

- **Same agent:** T3 forks the agent's real session (`native_fork`) if the agent supports it. The fork has full memory, tool calls included. Confirmed for Claude.
- **Different agent, or an agent without native forks (for example Cursor):** T3 sends a text handoff of the conversation (`portable_context`). Confirmed for Claude to Codex.

In the T3 UI, the fork shows the source history as inherited items.

## Limits

- Works only inside a T3 thread that has the `t3-code` MCP tools. If an ACP agent does not expose them, use the `acp-mcp-call` terminal fallback from T3's orchestration instructions.
- Only completed runs can be fork points, so the current turn can never be included.
- A fork always keeps history from the start of the conversation. There is no "last n turns only" mode.
- Sessions that T3 does not know about cannot be forked.
