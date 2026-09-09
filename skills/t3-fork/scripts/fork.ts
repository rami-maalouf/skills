#!/usr/bin/env bun
// fork (branch) or duplicate a t3 code conversation.
//
// how it works:
//   1. resolve the claude code session behind a t3 thread (t3 keeps the
//      session id in provider_session_runtime.resume_cursor_json).
//   2. copy the session transcript (~/.claude/projects/<slug>/<id>.jsonl)
//      to a new session id, optionally cut after the n-th user turn.
//   3. register the copy in t3 through its own transcript importer
//      (agentSessions.import over the local websocket rpc) so the history is
//      visible in the ui. the importer processes every transcript of the
//      project, so the other transcripts are shielded with temporary runtime
//      bindings that make the importer skip them, removed right after.
//
// usage:
//   bun run fork.ts [--current | --thread <t3-thread-id> | --session <claude-session-id>]
//                   [--list] [--up-to <n>] [--title <text>] [--no-register] [--dry-run]

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

type Args = {
  current: boolean;
  thread?: string;
  session?: string;
  list: boolean;
  upTo?: number;
  title?: string;
  register: boolean;
  dryRun: boolean;
};

function usage(exit = 0): never {
  console.log(`fork a t3 code conversation into a new thread

usage: bun run fork.ts [source] [options]

source (default: --current):
  --current             the conversation this script runs inside (walks the parent
                        claude process for --session-id / --resume), else the only
                        running t3 thread for the current directory
  --thread <id>         a t3 thread id
  --session <uuid>      a claude code session id

options:
  --list                print the user turns of the source and exit
  --up-to <n>           keep only the first n user turns (branch point)
  --title <text>        title for the new thread (default: "<source title> (fork)")
  --no-register         only write the transcript copy, do not create a t3 thread
  --dry-run             print what would happen, change nothing
  -h, --help            show this help`);
  process.exit(exit);
}

function parseArgs(argv: string[]): Args {
  const args: Args = { current: false, list: false, register: true, dryRun: false };
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
      case "--up-to": {
        const n = Number(next());
        if (!Number.isInteger(n) || n < 1) fail("--up-to expects a positive integer");
        args.upTo = n;
        break;
      }
      case "--title": args.title = next(); break;
      case "--no-register": args.register = false; break;
      case "--dry-run": args.dryRun = true; break;
      case "-h": case "--help": usage();
      default: fail(`unknown argument: ${a}`);
    }
  }
  const sources = [args.current, !!args.thread, !!args.session].filter(Boolean).length;
  if (sources > 1) fail("pick one of --current, --thread, --session");
  if (sources === 0) args.current = true;
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
         json_extract(r.resume_cursor_json, '$.resume') as session_id,
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

function findTranscript(sessionId: string): string {
  if (!existsSync(CLAUDE_PROJECTS)) fail(`claude projects directory not found at ${CLAUDE_PROJECTS}`);
  for (const dir of readdirSync(CLAUDE_PROJECTS)) {
    const candidate = join(CLAUDE_PROJECTS, dir, `${sessionId}.jsonl`);
    if (existsSync(candidate)) return candidate;
  }
  fail(`no transcript found for session ${sessionId} under ${CLAUDE_PROJECTS}`);
}

type Record = { [key: string]: any };

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

function textOf(content: unknown): string {
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
function isUserTurn(r: Record): boolean {
  if (r.type !== "user") return false;
  if (r.isMeta === true || r.isSidechain === true || r.isCompactSummary === true) return false;
  const content = r.message?.content;
  if (isToolResultOnly(content)) return false;
  return textOf(content).length > 0;
}

function userTurnIndices(records: Record[]): number[] {
  const out: number[] = [];
  records.forEach((r, i) => {
    if (isUserTurn(r)) out.push(i);
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
    if (!basename(file).startsWith("rollout-") || !recent(file)) continue;
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

// ---------- main ----------

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const db = openReadOnly();

  // 1. resolve the source session and (if any) its t3 thread
  let sessionId: string;
  let thread: ThreadRow | null = null;
  if (args.session) {
    if (!UUID_RE.test(args.session)) fail("--session expects a uuid");
    sessionId = args.session.toLowerCase();
    thread = threadBySession(db, sessionId);
  } else if (args.thread) {
    thread = threadById(db, args.thread);
    if (!thread) fail(`t3 thread ${args.thread} not found`);
    if (!thread.session_id) fail(`t3 thread ${args.thread} has no claude session yet (send one message first)`);
    sessionId = thread.session_id;
  } else {
    const fromProcess = sessionFromParentProcesses();
    if (fromProcess) {
      sessionId = fromProcess;
      thread = threadBySession(db, sessionId);
    } else {
      const running = runningThreadsForCwd(db, process.cwd());
      if (running.length === 0) fail(`no running t3 thread found for ${process.cwd()}; pass --thread or --session`);
      if (running.length > 1) {
        console.error("several running t3 threads for this directory, pass --thread <id>:");
        for (const t of running) console.error(`  ${t.thread_id}  ${t.title}`);
        process.exit(1);
      }
      thread = running[0];
      if (!thread.session_id) fail(`t3 thread ${thread.thread_id} has no claude session yet`);
      sessionId = thread.session_id;
    }
  }

  const srcPath = findTranscript(sessionId);
  const records = readTranscript(srcPath);
  const turns = userTurnIndices(records);
  const sourceTitle = thread?.title ?? transcriptTitle(records) ?? "untitled";

  if (args.list) {
    console.log(`source: ${sourceTitle}`);
    console.log(`session: ${sessionId}`);
    if (thread) console.log(`thread:  ${thread.thread_id}`);
    console.log(`user turns: ${turns.length}`);
    turns.forEach((idx, n) => {
      const r = records[idx];
      const when = typeof r.timestamp === "string" ? r.timestamp.replace("T", " ").slice(0, 16) : "";
      const text = textOf(r.message?.content).replace(/\s+/g, " ");
      console.log(`  ${String(n + 1).padStart(3)}  ${when}  ${text.length > 90 ? text.slice(0, 90) + "..." : text}`);
    });
    return;
  }

  if (turns.length === 0) fail("the source conversation has no user turns yet");
  if (args.upTo !== undefined && args.upTo > turns.length) fail(`--up-to ${args.upTo} exceeds the ${turns.length} user turns in the source`);

  // 2. build the copy
  const cut = args.upTo !== undefined && args.upTo < turns.length ? turns[args.upTo] : records.length;
  const keptTurns = args.upTo ?? turns.length;
  const newSessionId = crypto.randomUUID();
  const title = args.title ?? `${sourceTitle} (fork)`;
  const dstPath = join(dirname(srcPath), `${newSessionId}.jsonl`);
  const forked = rewriteSessionId(records.slice(0, cut), sessionId, newSessionId, title);

  // 3. figure out where the t3 thread goes
  const workspaceRoot = thread?.workspace_root ?? transcriptCwd(records);
  const cwd = thread?.cwd ?? transcriptCwd(records) ?? workspaceRoot;
  const project = thread ? { project_id: thread.project_id, workspace_root: thread.workspace_root } : workspaceRoot ? projectForWorkspace(db, workspaceRoot) : null;
  db.close();

  console.log(`source:   ${sourceTitle}`);
  console.log(`          session ${sessionId}${thread ? `, thread ${thread.thread_id}` : " (not bound to a t3 thread)"}`);
  console.log(`copy:     ${keptTurns}/${turns.length} user turns, ${forked.length}/${records.length} records`);
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
  const copiedDir = copySessionDir(join(dirname(srcPath), sessionId), join(dirname(srcPath), newSessionId), sessionId, newSessionId);
  if (copiedDir) console.log(`          copied subagent transcripts`);

  if (!args.register || !project) {
    console.log(`done. resume it with: claude --resume ${newSessionId}`);
    return;
  }

  // 4. register the copy through t3's importer so the history shows in the ui
  const app = findT3App();
  const origin = serverOrigin();
  const newThreadId = `import:claudeAgent:${newSessionId}`;
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
    if (summary) await dispatch(origin, issued.token, { type: "thread.unsettle", commandId: crypto.randomUUID(), threadId: newThreadId, reason: "user" });
    if (!summary) {
      unlinkSync(dstPath);
      rmSync(join(dirname(srcPath), newSessionId), { recursive: true, force: true });
      fail(`t3 did not import the copy (imported ${result.importedCount}, skipped ${result.skippedCount}); copy removed`);
    }
    console.log(`thread:   ${newThreadId}`);
    console.log(`          ${summary.messages} messages shown, ${blockers.length} other transcripts shielded, ${result.skippedCount} skipped by t3`);
  } finally {
    revokeToken(app, issued);
  }

  console.log("done. the new thread is in the t3 sidebar with its history; its first message continues the copied conversation.");
}

await main();
