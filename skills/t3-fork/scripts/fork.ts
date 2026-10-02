#!/usr/bin/env bun
// fork (branch) or duplicate a t3 code conversation, from claude code, codex,
// or cursor. by default the fork stays on the same agent as the source; pass
// --provider to hand it to a different one instead.
//
// how it works:
//   1. resolve the t3 thread (if any) and the agent + native session id behind it.
//      t3 keeps this in provider_session_runtime.resume_cursor_json - claude's
//      shape is {threadId, resume: <sessionId>}, codex's is {threadId: <sessionId>}.
//   2. same agent (default): copy the real session file (claude's
//      ~/.claude/projects/<slug>/<id>.jsonl, or codex's
//      ~/.codex/sessions/<y>/<m>/<d>/rollout-*.jsonl), optionally cut after the
//      n-th user turn, and register the copy in t3 through its own transcript
//      importer (agentSessions.import over the local websocket rpc) so the
//      history is visible in the ui. the importer processes every transcript
//      of the project, so the other transcripts are shielded with temporary
//      runtime bindings that make the importer skip them, removed right after.
//      cursor has no importable transcript format, so it always uses the
//      seeded path below even when it is also the source agent.
//   3. --provider (or a source agent with no native-resume support): codex,
//      cursor, and claude cannot read each other's session files, and cursor
//      has no t3-importable format at all, so there is no way to hand a live
//      session to a different agent, or "resume" cursor from a cold file.
//      instead this reads t3's own provider-agnostic message log
//      (projection_thread_messages - already clean role+text, no tool calls,
//      no system-reminder noise, regardless of which agent produced it),
//      renders the kept turns as plain text, and sends that as a brand-new
//      thread's first message. the new agent starts with that as context
//      rather than a resumed session.
//
// usage:
//   bun run fork.ts [--current | --thread <t3-thread-id> | --session <uuid>]
//                   [--list] [--first <n> | --last <n>] [--title <text>] [--no-register] [--dry-run]
//                   [--provider <name> [--model <name>]]

import { Database } from "bun:sqlite";
import { existsSync, readdirSync, statSync, cpSync, readFileSync, writeFileSync, unlinkSync, rmSync } from "node:fs";
import { homedir } from "node:os";
import { basename, dirname, join } from "node:path";
import { spawnSync } from "node:child_process";

const HOME = homedir();
const T3_HOME = process.env.T3CODE_HOME ?? join(HOME, ".t3");
const T3_DB = join(T3_HOME, "userdata", "state.sqlite");
const T3_RUNTIME = join(T3_HOME, "userdata", "server-runtime.json");
const CLAUDE_PROJECTS = join(HOME, ".claude", "projects");
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// default model per agent, mirroring t3's own DEFAULT_MODEL_BY_PROVIDER for the
// agents actually installed here. anything else needs an explicit --model.
const DEFAULT_MODEL_BY_PROVIDER: Record<string, string> = {
  codex: "gpt-5.6-sol",
  claudeAgent: "claude-sonnet-5",
  cursor: "default",
};

type Args = {
  current: boolean;
  thread?: string;
  session?: string;
  list: boolean;
  first?: number;
  last?: number;
  title?: string;
  register: boolean;
  dryRun: boolean;
  includeTrigger: boolean;
  provider?: string;
  model?: string;
};

function usage(exit = 0): never {
  console.log(`fork a t3 code conversation into a new thread

usage: bun run fork.ts [source] [options]

source (default: --current), works from claude code, codex, or cursor:
  --current             the conversation this script runs inside. walks the
                        parent process for a claude session id (precise even
                        with several claude threads in this directory); for
                        codex/cursor, or if that walk finds nothing, falls back
                        to the only running t3 thread for this directory
  --thread <id>         a t3 thread id (any agent)
  --session <uuid>      a native session id (claude or codex; a bare cursor
                        chat id is not supported, use --thread instead)

options:
  --list                print the user turns of the source and exit
  --first <n>           keep only the first n user turns, counting from the
                        start (branch point)
  --last <n>            keep only the last n user turns, counting from the end.
                        the new thread has no memory of anything before them
  --title <text>        title for the new thread (default: "<source title> (fork)")
  --no-register         only write the transcript copy, do not create a t3 thread
                        (with --provider: print what would be sent instead)
  --include-trigger     with --current, keep the last user turn (the message that
                        ran this command). by default it is dropped so the fork
                        does not start with its own invocation
  --provider <name>     fork into a new thread under a different agent (codex,
                        cursor, claudeAgent, ...) instead of the same-agent
                        default. codex and cursor cannot read a claude session
                        file or each other's, and cursor has no t3-importable
                        format at all (so it always uses this path even as the
                        default, same-agent target). the kept turns are sent as
                        plain text in the new thread's first message instead
  --model <name>        model for --provider (default: a sane per-provider
                        default for codex/cursor/claudeAgent; required for
                        other providers)
  --dry-run             print what would happen, change nothing
  -h, --help            show this help`);
  process.exit(exit);
}

function parseArgs(argv: string[]): Args {
  const args: Args = { current: false, list: false, register: true, dryRun: false, includeTrigger: false };
  const parseCount = (flag: string, value: string): number => {
    const n = Number(value);
    if (!Number.isInteger(n) || n < 1) fail(`${flag} expects a positive integer`);
    return n;
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => {
      const v = argv[++i];
      if (v === undefined) fail(`missing value for ${a}`);
      return v;
    };
    switch (a) {
      case "--current": args.current = true; break;
      case "--thread": args.thread = next(); break;
      case "--session": args.session = next(); break;
      case "--list": args.list = true; break;
      case "--first": args.first = parseCount(a, next()); break;
      case "--last": args.last = parseCount(a, next()); break;
      case "--title": args.title = next(); break;
      case "--no-register": args.register = false; break;
      case "--include-trigger": args.includeTrigger = true; break;
      case "--provider": args.provider = next(); break;
      case "--model": args.model = next(); break;
      case "--dry-run": args.dryRun = true; break;
      case "-h": case "--help": usage();
      default: fail(`unknown argument: ${a}`);
    }
  }
  const sources = [args.current, !!args.thread, !!args.session].filter(Boolean).length;
  if (sources > 1) fail("pick one of --current, --thread, --session");
  if (sources === 0) args.current = true;
  if (args.first !== undefined && args.last !== undefined) fail("pick one of --first, --last");
  if (args.model !== undefined && args.provider === undefined) fail("--model requires --provider");
  return args;
}

function fail(msg: string): never {
  console.error(`error: ${msg}`);
  process.exit(1);
}

// ---------- t3 state (read-only) ----------

type ThreadRow = {
  thread_id: string;
  project_id: string;
  title: string;
  branch: string | null;
  worktree_path: string | null;
  runtime_mode: string;
  interaction_mode: string;
  model_selection_json: string | null;
  workspace_root: string;
  provider: string | null;
  session_id: string | null;
  status: string | null;
  cwd: string | null;
};

function openReadOnly(): Database {
  if (!existsSync(T3_DB)) fail(`t3 state database not found at ${T3_DB}`);
  return new Database(T3_DB, { readonly: true });
}

const THREAD_SELECT = `
  select t.thread_id, t.project_id, t.title, t.branch, t.worktree_path,
         t.runtime_mode, t.interaction_mode, t.model_selection_json,
         p.workspace_root,
         r.provider_name as provider,
         -- claude's resume cursor is {threadId, resume: <sessionId>}; codex's is
         -- {threadId: <sessionId>} directly, with no "resume" key at all
         coalesce(json_extract(r.resume_cursor_json, '$.resume'), case when r.provider_name = 'codex' then json_extract(r.resume_cursor_json, '$.threadId') end) as session_id,
         r.status,
         json_extract(r.runtime_payload_json, '$.cwd') as cwd
  from projection_threads t
  join projection_projects p on p.project_id = t.project_id
  left join provider_session_runtime r on r.thread_id = t.thread_id
  where t.deleted_at is null`;

function threadById(db: Database, threadId: string): ThreadRow | null {
  return db.query<ThreadRow, [string]>(`${THREAD_SELECT} and t.thread_id = ?`).get(threadId);
}

function threadBySession(db: Database, sessionId: string): ThreadRow | null {
  return db.query<ThreadRow, [string]>(`${THREAD_SELECT} and json_extract(r.resume_cursor_json, '$.resume') = ?`).get(sessionId);
}

function runningThreadsForCwd(db: Database, cwd: string): ThreadRow[] {
  return db
    .query<ThreadRow, [string]>(`${THREAD_SELECT} and r.status = 'running' and json_extract(r.runtime_payload_json, '$.cwd') = ? order by t.updated_at desc`)
    .all(cwd);
}

function projectForWorkspace(db: Database, workspaceRoot: string): { project_id: string; workspace_root: string } | null {
  return db
    .query<{ project_id: string; workspace_root: string }, [string]>(
      `select project_id, workspace_root from projection_projects where deleted_at is null and workspace_root = ?`,
    )
    .get(workspaceRoot);
}

// ---------- current session detection ----------

function sessionFromParentProcesses(): string | null {
  let pid = process.ppid;
  for (let depth = 0; depth < 8 && pid > 1; depth++) {
    const out = spawnSync("ps", ["-o", "ppid=,command=", "-p", String(pid)], { encoding: "utf8" });
    if (out.status !== 0) return null;
    const line = out.stdout.trim();
    if (!line) return null;
    const m = line.match(/^\s*(\d+)\s+(.*)$/s);
    if (!m) return null;
    const command = m[2];
    if (/(^|\/)claude(\s|$)/.test(command) || command.includes("claude ")) {
      const flag = command.match(/--(?:session-id|resume)[= ]([0-9a-f-]{36})/i);
      if (flag) return flag[1].toLowerCase();
    }
    pid = Number(m[1]);
  }
  return null;
}

// ---------- transcript handling ----------

type Record = { [key: string]: any };

function findClaudeTranscript(sessionId: string): string | null {
  if (!existsSync(CLAUDE_PROJECTS)) return null;
  for (const dir of readdirSync(CLAUDE_PROJECTS)) {
    const candidate = join(CLAUDE_PROJECTS, dir, `${sessionId}.jsonl`);
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

function readTranscript(path: string): Record[] {
  const lines = readFileSync(path, "utf8").split("\n").filter((l) => l.trim().length > 0);
  return lines.map((line, i) => {
    try {
      return JSON.parse(line) as Record;
    } catch {
      fail(`could not parse line ${i + 1} of ${path}`);
    }
  });
}

function claudeTextOf(content: unknown): string {
  if (typeof content === "string") return content.trim();
  if (!Array.isArray(content)) return "";
  return content
    .filter((b) => b && typeof b === "object" && b.type === "text" && typeof b.text === "string")
    .map((b) => b.text)
    .join(" ")
    .trim();
}

function isToolResultOnly(content: unknown): boolean {
  return Array.isArray(content) && content.length > 0 && content.every((b) => b && typeof b === "object" && b.type === "tool_result");
}

// a user turn is a real prompt from the human: not a tool result, not meta, not a sidechain
function isClaudeUserTurn(r: Record): boolean {
  if (r.type !== "user") return false;
  if (r.isMeta === true || r.isSidechain === true || r.isCompactSummary === true) return false;
  const content = r.message?.content;
  if (isToolResultOnly(content)) return false;
  return claudeTextOf(content).length > 0;
}

function claudeUserTurnIndices(records: Record[]): number[] {
  const out: number[] = [];
  records.forEach((r, i) => {
    if (isClaudeUserTurn(r)) out.push(i);
  });
  return out;
}

function transcriptTitle(records: Record[]): string | null {
  let title: string | null = null;
  for (const r of records) if (typeof r.aiTitle === "string" && r.aiTitle.trim()) title = r.aiTitle.trim();
  return title;
}

function transcriptCwd(records: Record[]): string | null {
  for (const r of records) if (typeof r.cwd === "string" && r.cwd.trim()) return r.cwd.trim();
  return null;
}

function rewriteSessionId(records: Record[], from: string, to: string, title: string | null): Record[] {
  const hasTitle = records.some((r) => r.type === "ai-title");
  const withTitle = hasTitle || title === null ? records : [{ type: "ai-title", aiTitle: title, sessionId: from }, ...records];
  return withTitle.map((r) => {
    const copy = { ...r };
    if (copy.sessionId === from) copy.sessionId = to;
    if (title !== null && copy.type === "ai-title" && typeof copy.aiTitle === "string") copy.aiTitle = title;
    return copy;
  });
}

function writeTranscript(path: string, records: Record[]): void {
  writeFileSync(path, records.map((r) => JSON.stringify(r)).join("\n") + "\n");
}

// subagent transcripts live in <session-id>/subagents/*.jsonl next to the transcript
function copySessionDir(srcDir: string, dstDir: string, from: string, to: string): boolean {
  if (!existsSync(srcDir) || !statSync(srcDir).isDirectory()) return false;
  cpSync(srcDir, dstDir, { recursive: true });
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const p = join(dir, entry);
      if (statSync(p).isDirectory()) walk(p);
      else if (p.endsWith(".jsonl")) writeFileSync(p, readFileSync(p, "utf8").replaceAll(`"sessionId":"${from}"`, `"sessionId":"${to}"`));
    }
  };
  walk(dstDir);
  return true;
}

// ---------- codex transcript handling ----------
// codex stores sessions as "rollout" files under ~/.codex/sessions/<year>/<month>/<day>/
// rollout-<timestamp>-<id>.jsonl. unlike claude's format there is no parent-link
// chain to worry about when slicing, and text lives in "input_text"/"output_text"
// content blocks instead of "text" blocks.

function codexSessionsDir(): string {
  return join(process.env.CODEX_HOME ?? join(HOME, ".codex"), "sessions");
}

// codexSessionMeta and walkJsonl are declared later (used by the t3-import
// shielding step too); function declarations are hoisted, so this is fine.
function findCodexTranscript(sessionId: string): string | null {
  const files: string[] = [];
  walkJsonl(codexSessionsDir(), files);
  for (const file of files) {
    if (!basename(file).startsWith("rollout-")) continue;
    if (codexSessionMeta(file).id?.toLowerCase() === sessionId.toLowerCase()) return file;
  }
  return null;
}

function codexTextOf(content: unknown): string {
  if (typeof content === "string") return content.trim();
  if (!Array.isArray(content)) return "";
  return content
    .filter((b) => b && typeof b === "object" && (b.type === "input_text" || b.type === "output_text") && typeof b.text === "string")
    .map((b) => b.text)
    .join(" ")
    .trim();
}

// codex injects environment/plugin/instructions context as ordinary "user"
// role messages, indistinguishable from a real prompt except by content: they
// are always a bare xml-ish tag block or the project instructions header.
// there is no metadata flag to key off, unlike claude's isMeta/isSidechain.
const CODEX_SYNTHETIC_USER_RE = /^(<[a-zA-Z_]+>|# AGENTS\.md instructions for )/;

function isCodexUserTurn(r: Record): boolean {
  if (r.type !== "response_item" || r.payload?.type !== "message" || r.payload?.role !== "user") return false;
  const text = codexTextOf(r.payload.content);
  return text.length > 0 && !CODEX_SYNTHETIC_USER_RE.test(text);
}

function codexUserTurnIndices(records: Record[]): number[] {
  const out: number[] = [];
  records.forEach((r, i) => {
    if (isCodexUserTurn(r)) out.push(i);
  });
  return out;
}

function codexCwd(records: Record[]): string | null {
  for (const r of records) if (r.type === "session_meta" && typeof r.payload?.cwd === "string" && r.payload.cwd.trim()) return r.payload.cwd.trim();
  return null;
}

// rewrite the session_meta record(s) carrying the old session id; codex has no
// parent-link chain, so unlike claude's --last there is nothing else to fix up
function rewriteCodexSessionId(records: Record[], from: string, to: string): Record[] {
  return records.map((r) => {
    if (r.type !== "session_meta" || !r.payload) return r;
    const payload = { ...r.payload };
    if (payload.id === from) payload.id = to;
    if (payload.session_id === from) payload.session_id = to;
    return { ...r, payload };
  });
}

function codexRolloutFilename(sessionId: string): string {
  const ts = new Date().toISOString().replace(/:/g, "-").split(".")[0];
  return `rollout-${ts}-${sessionId}.jsonl`;
}

// ---------- t3 registration ----------

function findT3App(): string {
  const apps = readdirSync("/Applications").filter((n) => /^T3 Code.*\.app$/.test(n));
  if (apps.length === 0) fail("t3 code app not found in /Applications");
  return join("/Applications", apps[0]);
}

function t3Cli(app: string, args: string[]): string {
  const bin = join(app, "Contents", "MacOS", basename(app, ".app"));
  const script = join(app, "Contents", "Resources", "app.asar", "apps", "server", "dist", "bin.mjs");
  const out = spawnSync(bin, [script, ...args], { encoding: "utf8", env: { ...process.env, ELECTRON_RUN_AS_NODE: "1" } });
  if (out.status !== 0) fail(`t3 cli failed (${args.slice(0, 3).join(" ")}): ${out.stderr.trim()}`);
  return out.stdout;
}

type Issued = { token: string; sessionId: string };

function issueToken(app: string): Issued {
  const raw = t3Cli(app, ["auth", "session", "issue", "--base-dir", T3_HOME, "--json", "--ttl", "5m", "--label", "t3-fork"]);
  const parsed = JSON.parse(raw);
  const token: string | undefined = parsed.token ?? parsed.bearerToken ?? parsed.accessToken;
  const sessionId: string | undefined = parsed.sessionId ?? parsed.session?.sessionId;
  if (!token || !sessionId) fail("unexpected output from t3 auth session issue");
  return { token, sessionId };
}

function revokeToken(app: string, issued: Issued): void {
  try {
    t3Cli(app, ["auth", "session", "revoke", "--base-dir", T3_HOME, issued.sessionId]);
  } catch {
    // best effort: the token expires on its own after 5 minutes
  }
}

function serverOrigin(): string {
  if (!existsSync(T3_RUNTIME)) fail(`t3 code does not look like it is running (${T3_RUNTIME} missing)`);
  const rt = JSON.parse(readFileSync(T3_RUNTIME, "utf8"));
  if (typeof rt.origin !== "string") fail("could not read server origin from server-runtime.json");
  return rt.origin;
}

type WsTicket = { ticket: string };

async function wsTicket(origin: string, token: string): Promise<string> {
  const res = await fetch(`${origin}/api/auth/websocket-ticket`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: "{}",
  });
  if (!res.ok) fail(`could not get a websocket ticket (${res.status})`);
  return ((await res.json()) as WsTicket).ticket;
}

// minimal effect-rpc client over t3's json websocket: one request, one exit
function rpcCall(origin: string, ticket: string, tag: string, payload: unknown): Promise<any> {
  return new Promise((resolve, reject) => {
    const url = `${origin.replace(/^http/, "ws")}/ws?wsTicket=${encodeURIComponent(ticket)}`;
    const ws = new WebSocket(url);
    const timer = setTimeout(() => {
      ws.close();
      reject(new Error(`t3 rpc ${tag} timed out`));
    }, 120_000);
    ws.onopen = () => ws.send(JSON.stringify({ _tag: "Request", id: "1", tag, payload, headers: [] }));
    ws.onerror = () => {
      clearTimeout(timer);
      reject(new Error(`websocket error while calling ${tag}`));
    };
    ws.onmessage = (ev) => {
      for (const line of String(ev.data).split("\n").filter((l) => l.trim())) {
        const msg = JSON.parse(line);
        if (msg._tag === "Exit") {
          clearTimeout(timer);
          ws.close();
          if (msg.exit?._tag === "Success") resolve(msg.exit.value);
          else reject(new Error(`t3 rpc ${tag} failed: ${JSON.stringify(msg.exit).slice(0, 500)}`));
        } else if (msg._tag === "Defect") {
          clearTimeout(timer);
          ws.close();
          reject(new Error(`t3 rpc ${tag} defect: ${JSON.stringify(msg.defect).slice(0, 500)}`));
        }
      }
    };
  });
}

// t3's importer treats a transcript as eligible when its first cwd is the project
// root (compared by inode), its mtime is within 30 days, and it is not imported yet
const RECENT_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;

function firstCwd(path: string): string | null {
  const fd = readFileSync(path, "utf8");
  for (const line of fd.split("\n")) {
    if (!line.trim()) continue;
    try {
      const r = JSON.parse(line);
      const cwd = typeof r.cwd === "string" ? r.cwd.trim() : "";
      if (cwd) return cwd;
    } catch {
      // ignore unparsable lines, like the scanner does
    }
  }
  return null;
}

function firstSessionId(path: string): string | null {
  for (const line of readFileSync(path, "utf8").split("\n")) {
    if (!line.trim()) continue;
    try {
      const r = JSON.parse(line);
      if (typeof r.sessionId === "string" && UUID_RE.test(r.sessionId)) return r.sessionId.toLowerCase();
    } catch {
      // skip
    }
  }
  return null;
}

function dirIdentity(path: string): string | null {
  try {
    const st = statSync(path);
    return st.isDirectory() ? `${st.dev}:${st.ino}` : null;
  } catch {
    return null;
  }
}

type OtherSession = { provider: "claudeAgent" | "codex"; sessionId: string };

function walkJsonl(dir: string, out: string[]): void {
  if (!existsSync(dir)) return;
  for (const entry of readdirSync(dir)) {
    const p = join(dir, entry);
    const st = statSync(p);
    if (st.isDirectory()) walkJsonl(p, out);
    else if (entry.endsWith(".jsonl")) out.push(p);
  }
}

// first record of a codex rollout carries the session id and cwd
function codexSessionMeta(path: string): { id: string | null; cwd: string | null } {
  for (const line of readFileSync(path, "utf8").split("\n")) {
    if (!line.trim()) continue;
    try {
      const r = JSON.parse(line);
      if (r.type === "session_meta") {
        const id = r.payload?.id ?? r.payload?.session_id;
        const cwd = r.payload?.cwd;
        return { id: typeof id === "string" ? id.trim() : null, cwd: typeof cwd === "string" ? cwd.trim() : null };
      }
    } catch {
      // skip
    }
  }
  return { id: null, cwd: null };
}

// every other transcript t3's importer would pick up for this project:
// claude code sessions under ~/.claude/projects and codex rollouts under ~/.codex/sessions
function otherEligibleSessions(workspaceRoot: string, excludePath: string): OtherSession[] {
  const rootId = dirIdentity(workspaceRoot);
  if (!rootId) return [];
  const now = Date.now();
  const recent = (file: string) => {
    const st = statSync(file);
    return st.isFile() && st.mtimeMs <= now && st.mtimeMs >= now - RECENT_WINDOW_MS;
  };
  const seen = new Set<string>();
  const out: OtherSession[] = [];
  const add = (provider: OtherSession["provider"], sessionId: string | null) => {
    if (!sessionId) return;
    const key = `${provider}:${sessionId.toLowerCase()}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ provider, sessionId: sessionId.toLowerCase() });
  };

  if (existsSync(CLAUDE_PROJECTS)) {
    for (const dir of readdirSync(CLAUDE_PROJECTS)) {
      const full = join(CLAUDE_PROJECTS, dir);
      if (!statSync(full).isDirectory()) continue;
      for (const entry of readdirSync(full)) {
        if (!entry.endsWith(".jsonl")) continue;
        const file = join(full, entry);
        if (file === excludePath || !recent(file)) continue;
        const cwd = firstCwd(file);
        if (!cwd || dirIdentity(cwd) !== rootId) continue;
        add("claudeAgent", basename(entry, ".jsonl"));
        add("claudeAgent", firstSessionId(file));
      }
    }
  }

  const codexFiles: string[] = [];
  walkJsonl(join(process.env.CODEX_HOME ?? join(HOME, ".codex"), "sessions"), codexFiles);
  for (const file of codexFiles) {
    if (!basename(file).startsWith("rollout-") || file === excludePath || !recent(file)) continue;
    const meta = codexSessionMeta(file);
    if (!meta.cwd || dirIdentity(meta.cwd) !== rootId) continue;
    add("codex", meta.id);
  }
  return out;
}

const BLOCKER_INSTANCE = "t3-fork-blocker";

// a binding whose provider instance does not match makes the importer skip that
// transcript with a warning instead of creating a duplicate thread.
// - no binding yet: insert a placeholder row
// - binding of a deleted import thread: retag it as "t3-fork-blocker:<original>"
//   so the importer does not resurrect the thread; the suffix lets us restore it
// - binding of a visible import thread: leave it, the importer treats it as done
function insertBlockers(sessions: OtherSession[]): string[] {
  const db = new Database(T3_DB);
  const shielded: string[] = [];
  try {
    db.exec("pragma busy_timeout = 5000");
    const insert = db.query(
      `insert into provider_session_runtime
         (thread_id, provider_name, provider_instance_id, adapter_key, runtime_mode, status, last_seen_at, resume_cursor_json, runtime_payload_json)
       values (?, 'claudeAgent', '${BLOCKER_INSTANCE}', 'claudeAgent', 'full-access', 'stopped', ?, null, '{}')
       on conflict (thread_id) do nothing`,
    );
    const existing = db.query<{ provider_instance_id: string | null; visible: number }, [string, string]>(
      `select r.provider_instance_id,
              exists(select 1 from projection_threads t where t.thread_id = ? and t.deleted_at is null) as visible
       from provider_session_runtime r where r.thread_id = ?`,
    );
    const retag = db.query(`update provider_session_runtime set provider_instance_id = ? where thread_id = ?`);
    const now = new Date().toISOString();
    for (const s of sessions) {
      const threadId = `import:${s.provider}:${s.sessionId}`;
      if (insert.run(threadId, now).changes > 0) {
        shielded.push(threadId);
        continue;
      }
      const row = existing.get(threadId, threadId);
      if (!row || row.visible) continue;
      const original = row.provider_instance_id ?? "";
      if (original.startsWith(BLOCKER_INSTANCE)) continue;
      retag.run(`${BLOCKER_INSTANCE}:${original}`, threadId);
      shielded.push(threadId);
    }
  } finally {
    db.close();
  }
  return shielded;
}

// undo insertBlockers: drop placeholder rows, restore retagged rows
function removeBlockers(): number {
  const db = new Database(T3_DB);
  try {
    db.exec("pragma busy_timeout = 5000");
    const rows = db
      .query<{ thread_id: string; provider_instance_id: string }, []>(
        `select thread_id, provider_instance_id from provider_session_runtime where provider_instance_id like '${BLOCKER_INSTANCE}%'`,
      )
      .all();
    const del = db.query(`delete from provider_session_runtime where thread_id = ?`);
    const restore = db.query(`update provider_session_runtime set provider_instance_id = ? where thread_id = ?`);
    for (const row of rows) {
      if (row.provider_instance_id === BLOCKER_INSTANCE) del.run(row.thread_id);
      else restore.run(row.provider_instance_id.slice(BLOCKER_INSTANCE.length + 1) || null, row.thread_id);
    }
    return rows.length;
  } finally {
    db.close();
  }
}

function visibleImportThreadIds(): Set<string> {
  const db = new Database(T3_DB, { readonly: true });
  try {
    return new Set(db.query<{ thread_id: string }, []>(`select thread_id from projection_threads where thread_id like 'import:%' and deleted_at is null`).all().map((r) => r.thread_id));
  } finally {
    db.close();
  }
}

async function dispatch(origin: string, token: string, command: Record): Promise<void> {
  const res = await fetch(`${origin}/api/orchestration/dispatch`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}`, "content-type": "application/json" },
    body: JSON.stringify(command),
  });
  if (!res.ok) fail(`t3 dispatch ${command.type} failed (${res.status}): ${await res.text()}`);
}

function importedThreadSummary(threadId: string): { title: string; messages: number } | null {
  const db = new Database(T3_DB, { readonly: true });
  try {
    return db
      .query<{ title: string; messages: number }, [string, string]>(
        `select t.title, (select count(*) from projection_thread_messages m where m.thread_id = ?) as messages
         from projection_threads t where t.thread_id = ? and t.deleted_at is null`,
      )
      .get(threadId, threadId);
  } finally {
    db.close();
  }
}

// ---------- provider-agnostic message history (used for --provider / cursor forks) ----------
// t3 keeps a clean, already-deduplicated role+text log per thread regardless of
// which agent produced it. no tool calls, no system-reminder noise: this is
// exactly what a different agent (or a --list preview) should see.

type DbMessage = { role: "user" | "assistant"; text: string };

function dbThreadMessages(threadId: string): DbMessage[] {
  const db = new Database(T3_DB, { readonly: true });
  try {
    return db
      .query<{ role: string; text: string }, [string]>(
        `select role, text from projection_thread_messages
         where thread_id = ? and role in ('user', 'assistant') and text != ''
         order by created_at, message_id`,
      )
      .all(threadId)
      .map((r) => ({ role: r.role as "user" | "assistant", text: r.text }));
  } finally {
    db.close();
  }
}

// ---------- cross-agent / seeded fork (used when no native resume applies) ----------

type ProviderForkInput = {
  args: Args;
  provider: string;
  sourceTitle: string;
  messages: DbMessage[];
  rangeStart: number;
  rangeEnd: number;
  totalUserTurns: number;
  keptTurns: number;
  droppedTrigger: boolean;
  project: { project_id: string; workspace_root: string } | null;
  thread: ThreadRow | null;
};

async function runProviderFork(input: ProviderForkInput): Promise<void> {
  const { args, provider, sourceTitle, messages, rangeStart, rangeEnd, totalUserTurns, keptTurns, droppedTrigger, project, thread } = input;
  const model = args.model ?? DEFAULT_MODEL_BY_PROVIDER[provider];
  if (!model) {
    fail(
      `no default model known for provider "${provider}"; pass --model explicitly ` +
        `(known defaults: ${Object.keys(DEFAULT_MODEL_BY_PROVIDER).join(", ")})`,
    );
  }
  const rendered = messages
    .slice(rangeStart, rangeEnd)
    .map((m) => `${m.role === "user" ? "User" : "Assistant"}: ${m.text}`)
    .join("\n\n");
  if (!rendered) fail("nothing to send: the kept turns have no user or assistant text");
  const title = args.title ?? `${sourceTitle} (fork → ${provider})`;
  const rangeNote = args.last !== undefined ? " (last)" : "";

  console.log(`source:   ${sourceTitle}`);
  console.log(`          ${totalUserTurns} user turns total${thread ? `, thread ${thread.thread_id}` : ""}`);
  console.log(`copy:     ${keptTurns}/${totalUserTurns} user turns${rangeNote}, sent as plain text${droppedTrigger ? " (dropped the turn that triggered this fork)" : ""}`);
  console.log(`title:    ${title}`);
  console.log(`agent:    ${provider} / ${model} (fresh thread, no native resume)`);

  if (!args.register || args.dryRun) {
    console.log(args.dryRun ? "dry run: nothing sent" : "register: skipped (--no-register)");
    console.log("--- message that would be sent ---");
    console.log(rendered);
    return;
  }
  if (!project) fail(`no t3 project matches the source's workspace root; open it as a t3 project first`);
  console.log(`project:  ${project.workspace_root}`);

  const app = findT3App();
  const origin = serverOrigin();
  const threadId = crypto.randomUUID();
  const modelSelection = { instanceId: provider, model };
  const runtimeMode = thread?.runtime_mode ?? "full-access";
  const interactionMode = thread?.interaction_mode ?? "default";
  const issued = issueToken(app);
  try {
    await dispatch(origin, issued.token, {
      type: "thread.create",
      commandId: crypto.randomUUID(),
      threadId,
      projectId: project.project_id,
      title,
      modelSelection,
      runtimeMode,
      interactionMode,
      branch: thread?.branch ?? null,
      worktreePath: thread?.worktree_path ?? null,
      createdAt: new Date().toISOString(),
    });
    await dispatch(origin, issued.token, {
      type: "thread.turn.start",
      commandId: crypto.randomUUID(),
      threadId,
      message: { messageId: crypto.randomUUID(), role: "user", text: rendered, attachments: [] },
      modelSelection,
      titleSeed: title,
      runtimeMode,
      interactionMode,
      createdAt: new Date().toISOString(),
    });
  } catch (e) {
    await dispatch(origin, issued.token, { type: "thread.delete", commandId: crypto.randomUUID(), threadId }).catch(() => {});
    throw e;
  } finally {
    revokeToken(app, issued);
  }

  console.log(`thread:   ${threadId}`);
  console.log(`done. ${provider} is starting a fresh session with the copied conversation as its first message.`);
}

// ---------- native resume (same agent: claude or codex) ----------
// resumes the real session file, so the new thread has true native memory
// (tool calls included), not just a pasted text digest. this is only possible
// when the source and target are the same agent, and only claude and codex
// have a t3-importable transcript format; cursor always uses runProviderFork.

type NativeForkInput = {
  args: Args;
  provider: "claudeAgent" | "codex";
  sessionId: string;
  sourceTitle: string;
  records: Record[];
  rangeStart: number;
  rangeEnd: number;
  keptTurns: number;
  totalUserTurns: number;
  droppedTrigger: boolean;
  srcPath: string;
  project: { project_id: string; workspace_root: string } | null;
  workspaceRoot: string | null;
  thread: ThreadRow | null;
};

async function runNativeFork(input: NativeForkInput): Promise<void> {
  const { args, provider, sessionId, sourceTitle, records, rangeStart, rangeEnd, keptTurns, totalUserTurns, droppedTrigger, srcPath, project, workspaceRoot, thread } = input;
  const newSessionId = crypto.randomUUID();
  const title = args.title ?? `${sourceTitle} (fork)`;
  const rawSlice = records.slice(rangeStart, rangeEnd);
  let forked: Record[];
  let dstPath: string;
  let needsTitleFix: boolean;

  if (provider === "claudeAgent") {
    // --first keeps a prefix (records already start at the session's real
    // beginning, so the parent chain is intact); --last keeps a suffix and
    // needs its first record's parent link cleared, since that parent falls
    // outside the slice.
    if (rangeStart > 0 && "parentUuid" in rawSlice[0]) rawSlice[0] = { ...rawSlice[0], parentUuid: null };
    // t3's importer only accepts a transcript whose first cwd is the project root. a
    // --last slice may start in a subfolder the conversation had moved into, so the
    // first kept record with a cwd gets the source's root cwd back.
    if (rangeStart > 0) {
      const rootCwd = transcriptCwd(records);
      const i = rawSlice.findIndex((r) => typeof r.cwd === "string" && r.cwd.trim());
      if (rootCwd && i >= 0 && rawSlice[i].cwd !== rootCwd) rawSlice[i] = { ...rawSlice[i], cwd: rootCwd };
    }
    forked = rewriteSessionId(rawSlice, sessionId, newSessionId, title);
    dstPath = join(dirname(srcPath), `${newSessionId}.jsonl`);
    needsTitleFix = false; // the injected ai-title record already carries the title
  } else {
    // codex has no parent-link chain, so a --last slice needs no fix-up
    forked = rewriteCodexSessionId(rawSlice, sessionId, newSessionId);
    dstPath = join(dirname(srcPath), codexRolloutFilename(newSessionId));
    needsTitleFix = true; // codex's own importer derives a title; overwrite it after
  }

  console.log(`source:   ${sourceTitle}`);
  console.log(`          ${provider} session ${sessionId}${thread ? `, thread ${thread.thread_id}` : " (not bound to a t3 thread)"}`);
  const rangeNote = args.last !== undefined ? " (last)" : "";
  console.log(`copy:     ${keptTurns}/${totalUserTurns} user turns${rangeNote}, ${forked.length}/${records.length} records${droppedTrigger ? " (dropped the turn that triggered this fork)" : ""}`);
  console.log(`          ${dstPath}`);
  console.log(`title:    ${title}`);

  if (!args.register) {
    console.log("register: skipped (--no-register)");
  } else if (!project) {
    fail(`no t3 project matches workspace root ${workspaceRoot ?? "(unknown)"}; add the project in t3 or use --no-register`);
  } else {
    console.log(`project:  ${project.workspace_root}`);
  }

  if (args.dryRun) {
    console.log("dry run: nothing written");
    return;
  }

  writeTranscript(dstPath, forked);
  if (provider === "claudeAgent") {
    const copiedDir = copySessionDir(join(dirname(srcPath), sessionId), join(dirname(srcPath), newSessionId), sessionId, newSessionId);
    if (copiedDir) console.log(`          copied subagent transcripts`);
  }

  if (!args.register || !project) {
    const resumeHint = provider === "claudeAgent" ? `claude --resume ${newSessionId}` : `codex resume ${newSessionId}`;
    console.log(`done. resume it with: ${resumeHint}`);
    return;
  }

  // register the copy through t3's importer so the history shows in the ui
  const app = findT3App();
  const origin = serverOrigin();
  const newThreadId = `import:${provider}:${newSessionId}`;
  const issued = issueToken(app);
  try {
    const ticket = await wsTicket(origin, issued.token);
    // scan refreshes the importer's transcript cache so it sees the new file
    await rpcCall(origin, ticket, "agentSessions.scan", {});
    const others = otherEligibleSessions(project.workspace_root, dstPath);
    const before = visibleImportThreadIds();
    removeBlockers();
    const blockers = insertBlockers(others);
    let result: { importedCount: number; skippedCount: number };
    try {
      result = await rpcCall(origin, await wsTicket(origin, issued.token), "agentSessions.import", {
        projectId: project.project_id,
        expectedWorkspaceRoot: project.workspace_root,
      });
    } finally {
      removeBlockers();
    }
    // safety net: the importer is all-or-nothing, remove anything it created besides our copy
    const unexpected = [...visibleImportThreadIds()].filter((id) => id !== newThreadId && !before.has(id));
    for (const id of unexpected) {
      console.error(`warning: importer also created ${id}; deleting it`);
      await dispatch(origin, issued.token, { type: "thread.delete", commandId: crypto.randomUUID(), threadId: id });
    }
    const summary = importedThreadSummary(newThreadId);
    // the importer marks threads as settled, which hides them in the sidebar's
    // collapsed "settled" group; unsettle so the fork shows up with active threads
    if (summary) {
      await dispatch(origin, issued.token, { type: "thread.unsettle", commandId: crypto.randomUUID(), threadId: newThreadId, reason: "user" });
      if (needsTitleFix) await dispatch(origin, issued.token, { type: "thread.meta.update", commandId: crypto.randomUUID(), threadId: newThreadId, title });
    }
    if (!summary) {
      unlinkSync(dstPath);
      if (provider === "claudeAgent") rmSync(join(dirname(srcPath), newSessionId), { recursive: true, force: true });
      fail(`t3 did not import the copy (imported ${result.importedCount}, skipped ${result.skippedCount}); copy removed`);
    }
    console.log(`thread:   ${newThreadId}`);
    console.log(`          ${summary.messages} messages shown, ${blockers.length} other transcripts shielded, ${result.skippedCount} skipped by t3`);
  } finally {
    revokeToken(app, issued);
  }

  console.log("done. the new thread is in the t3 sidebar with its history; its first message continues the copied conversation.");
}

// ---------- main ----------

const NATIVE_PROVIDERS = new Set(["claudeAgent", "codex"]);

function findNativeTranscript(provider: string, sessionId: string): string | null {
  return provider === "claudeAgent" ? findClaudeTranscript(sessionId) : findCodexTranscript(sessionId);
}

function nativeUserTurnIndices(provider: string, records: Record[]): number[] {
  return provider === "claudeAgent" ? claudeUserTurnIndices(records) : codexUserTurnIndices(records);
}

// where --first/--last/the default trigger-drop land, shared by both the
// native (turn-index-based) and seeded (db-row-based) paths
function resolveRange(totalTurns: number, turnIndex: (n: number) => number, endIndex: number, args: Args): {
  rangeStart: number; rangeEnd: number; keptTurns: number; droppedTrigger: boolean;
} {
  let first = args.first;
  let droppedTrigger = false;
  if (first === undefined && args.last === undefined && args.current && !args.includeTrigger && totalTurns > 1) {
    first = totalTurns - 1;
    droppedTrigger = true;
  }
  if (args.last !== undefined) return { rangeStart: turnIndex(totalTurns - args.last), rangeEnd: endIndex, keptTurns: args.last, droppedTrigger };
  const rangeEnd = first !== undefined && first < totalTurns ? turnIndex(first) : endIndex;
  return { rangeStart: 0, rangeEnd, keptTurns: first ?? totalTurns, droppedTrigger };
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const db = openReadOnly();

  // 1. resolve the source: a t3 thread (if any), its agent, and its native
  // session id (if the agent has one and needs one for a native resume).
  let thread: ThreadRow | null = null;
  let sourceProvider: string | null = null;
  let sessionId: string | null = null;

  if (args.session) {
    if (!UUID_RE.test(args.session)) fail("--session expects a uuid");
    sessionId = args.session.toLowerCase();
    thread = threadBySession(db, sessionId);
    if (thread) sourceProvider = thread.provider;
    else if (findClaudeTranscript(sessionId)) sourceProvider = "claudeAgent";
    else if (findCodexTranscript(sessionId)) sourceProvider = "codex";
    else fail(`session ${sessionId} not found under claude or codex transcripts, and no t3 thread references it`);
  } else if (args.thread) {
    thread = threadById(db, args.thread);
    if (!thread) fail(`t3 thread ${args.thread} not found`);
    sourceProvider = thread.provider;
    sessionId = thread.session_id;
    if (!sourceProvider) fail(`t3 thread ${args.thread} has no provider session yet (send one message first)`);
  } else {
    // claude only: cheap and precise when it works (picks the exact session
    // even if several claude threads share this cwd, e.g. subagents).
    // codex/cursor fall through to the cwd lookup below, which is fully
    // provider-agnostic and already correct for them.
    const fromProcess = sessionFromParentProcesses();
    if (fromProcess) {
      sessionId = fromProcess;
      thread = threadBySession(db, sessionId);
      sourceProvider = thread?.provider ?? "claudeAgent";
    } else {
      const running = runningThreadsForCwd(db, process.cwd());
      if (running.length === 0) fail(`no running t3 thread found for ${process.cwd()}; pass --thread or --session`);
      if (running.length > 1) {
        console.error("several running t3 threads for this directory, pass --thread <id>:");
        for (const t of running) console.error(`  ${t.thread_id}  ${t.title} (${t.provider ?? "unknown"})`);
        process.exit(1);
      }
      thread = running[0];
      sourceProvider = thread.provider;
      sessionId = thread.session_id;
      if (!sourceProvider) fail(`t3 thread ${thread.thread_id} has no provider session yet`);
    }
  }
  if (!sourceProvider) fail("could not determine which agent this conversation belongs to");

  const targetProvider = args.provider ?? sourceProvider;
  const useNative = targetProvider === sourceProvider && NATIVE_PROVIDERS.has(sourceProvider);
  const sourceTitle = thread?.title ?? "untitled";

  // ---- --list: preview turns without changing anything ----
  if (args.list) {
    if (thread) {
      const messages = dbThreadMessages(thread.thread_id);
      console.log(`source: ${sourceTitle}`);
      console.log(`thread: ${thread.thread_id} (${sourceProvider})`);
      console.log(`user turns: ${messages.filter((m) => m.role === "user").length}`);
      let n = 0;
      for (const m of messages) {
        if (m.role !== "user") continue;
        n += 1;
        const text = m.text.replace(/\s+/g, " ");
        console.log(`  ${String(n).padStart(3)}  ${text.length > 90 ? text.slice(0, 90) + "..." : text}`);
      }
    } else {
      if (!sessionId) fail("nothing to list");
      const srcPath = findNativeTranscript(sourceProvider, sessionId);
      if (!srcPath) fail(`no ${sourceProvider} transcript found for session ${sessionId}`);
      const records = readTranscript(srcPath);
      const turns = nativeUserTurnIndices(sourceProvider, records);
      const textOfTurn = (r: Record) => (sourceProvider === "claudeAgent" ? claudeTextOf(r.message?.content) : codexTextOf(r.payload?.content));
      console.log(`source: ${sourceProvider === "claudeAgent" ? (transcriptTitle(records) ?? "untitled") : "untitled"}`);
      console.log(`session: ${sessionId} (${sourceProvider}, not bound to a t3 thread)`);
      console.log(`user turns: ${turns.length}`);
      turns.forEach((idx, i) => {
        const text = textOfTurn(records[idx]).replace(/\s+/g, " ");
        console.log(`  ${String(i + 1).padStart(3)}  ${text.length > 90 ? text.slice(0, 90) + "..." : text}`);
      });
    }
    db.close();
    return;
  }

  // ---- native resume: same agent, real session file, full fidelity ----
  if (useNative) {
    if (!sessionId) fail(`no ${sourceProvider} session id available for this source`);
    const srcPath = findNativeTranscript(sourceProvider, sessionId);
    if (!srcPath) fail(`no ${sourceProvider} transcript found for session ${sessionId}`);
    const records = readTranscript(srcPath);
    const turns = nativeUserTurnIndices(sourceProvider, records);
    if (turns.length === 0) fail("the source conversation has no user turns yet");
    if (args.first !== undefined && args.first > turns.length) fail(`--first ${args.first} exceeds the ${turns.length} user turns in the source`);
    if (args.last !== undefined && args.last > turns.length) fail(`--last ${args.last} exceeds the ${turns.length} user turns in the source`);
    const { rangeStart, rangeEnd, keptTurns, droppedTrigger } = resolveRange(turns.length, (n) => turns[n], records.length, args);

    const resolvedTitle = thread?.title ?? (sourceProvider === "claudeAgent" ? transcriptTitle(records) : null) ?? "untitled";
    const workspaceRoot = thread?.workspace_root ?? (sourceProvider === "claudeAgent" ? transcriptCwd(records) : codexCwd(records));
    const project = thread
      ? { project_id: thread.project_id, workspace_root: thread.workspace_root }
      : workspaceRoot
        ? projectForWorkspace(db, workspaceRoot)
        : null;
    db.close();

    await runNativeFork({
      args, provider: sourceProvider as "claudeAgent" | "codex", sessionId, sourceTitle: resolvedTitle, records,
      rangeStart, rangeEnd, keptTurns, totalUserTurns: turns.length, droppedTrigger, srcPath, project, workspaceRoot, thread,
    });
    return;
  }

  // ---- seeded fork: different agent, or an agent (cursor) with no t3-importable
  // transcript format. driven entirely by t3's own provider-agnostic message
  // log, so it works no matter which agent produced the source conversation.
  if (!thread) fail(`${targetProvider} forks need message history from a t3 thread; run this from inside a t3 thread, or pass --thread`);
  const messages = dbThreadMessages(thread.thread_id);
  const userIdx: number[] = [];
  messages.forEach((m, i) => {
    if (m.role === "user") userIdx.push(i);
  });
  if (userIdx.length === 0) fail("the source conversation has no user turns yet");
  if (args.first !== undefined && args.first > userIdx.length) fail(`--first ${args.first} exceeds the ${userIdx.length} user turns in the source`);
  if (args.last !== undefined && args.last > userIdx.length) fail(`--last ${args.last} exceeds the ${userIdx.length} user turns in the source`);
  const { rangeStart, rangeEnd, keptTurns, droppedTrigger } = resolveRange(userIdx.length, (n) => userIdx[n], messages.length, args);

  const project = { project_id: thread.project_id, workspace_root: thread.workspace_root };
  db.close();

  await runProviderFork({
    args, provider: targetProvider, sourceTitle, messages, rangeStart, rangeEnd,
    totalUserTurns: userIdx.length, keptTurns, droppedTrigger, project, thread,
  });
}

await main();
