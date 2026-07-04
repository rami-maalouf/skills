#!/usr/bin/env python3
"""extract rami's own messages from claude code transcripts.

walks ~/.claude/projects/*/*.jsonl and writes one markdown file per project
containing only the human-authored messages, chronologically, plus an
index.md ranking projects by volume. stdlib only.

usage:
    python3 extract_conversations.py --out /path/to/corpus
"""

import argparse
import json
from datetime import datetime
from pathlib import Path

PROJECTS_DIR = Path.home() / ".claude" / "projects"
MAX_MSG_CHARS = 4000

# harness noise that shows up as user messages but isn't rami talking
NOISE_PREFIXES = (
    "<command-name>",
    "<local-command-stdout",
    "<system-reminder>",
    "<task-notification>",
    "Caveat: The messages below",
    "[Request interrupted",
    "API Error",
    "Base directory for this skill:",
)


def message_texts(msg):
    """yield human text from a user message's content field."""
    content = msg.get("content")
    if isinstance(content, str):
        yield content
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                yield block.get("text", "")


def is_noise(text):
    stripped = text.strip()
    if not stripped:
        return True
    return any(stripped.startswith(p) for p in NOISE_PREFIXES)


def extract_project(project_dir):
    """return list of (timestamp, text) for one project, deduped and sorted."""
    seen = set()
    messages = []
    for jsonl in sorted(project_dir.glob("*.jsonl")):
        try:
            lines = jsonl.read_text(errors="replace").splitlines()
        except OSError:
            continue
        for line in lines:
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if entry.get("type") != "user" or entry.get("isSidechain"):
                continue
            ts = entry.get("timestamp", "")
            for text in message_texts(entry.get("message", {})):
                if is_noise(text):
                    continue
                key = (ts, text[:80])
                if key in seen:
                    continue
                seen.add(key)
                if len(text) > MAX_MSG_CHARS:
                    text = text[:MAX_MSG_CHARS] + "\n[truncated]"
                messages.append((ts, text.strip()))
    messages.sort(key=lambda m: m[0])
    return messages


def day_of(ts):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except ValueError:
        return "unknown-date"


def write_project_file(out_dir, slug, messages):
    path = out_dir / f"{slug}.md"
    parts = [f"# {slug}\n"]
    current_day = None
    for ts, text in messages:
        day = day_of(ts)
        if day != current_day:
            parts.append(f"\n## {day}\n")
            current_day = day
        parts.append(f"\n{text}\n\n---\n")
    path.write_text("".join(parts))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="output directory for the corpus")
    parser.add_argument(
        "--projects-dir", default=str(PROJECTS_DIR), help="claude projects dir"
    )
    args = parser.parse_args()

    projects_dir = Path(args.projects_dir).expanduser()
    out_dir = Path(args.out).expanduser()
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for project_dir in sorted(projects_dir.iterdir()):
        if not project_dir.is_dir():
            continue
        messages = extract_project(project_dir)
        if not messages:
            continue
        slug = project_dir.name.lstrip("-")
        write_project_file(out_dir, slug, messages)
        words = sum(len(t.split()) for _, t in messages)
        rows.append(
            {
                "slug": slug,
                "messages": len(messages),
                "words": words,
                "first": day_of(messages[0][0]),
                "last": day_of(messages[-1][0]),
            }
        )

    rows.sort(key=lambda r: r["words"], reverse=True)

    index = ["# corpus index\n\n| project | messages | words | first | last |",
             "|---|---|---|---|---|"]
    for r in rows:
        index.append(
            f"| [{r['slug']}]({r['slug']}.md) | {r['messages']} "
            f"| {r['words']} | {r['first']} | {r['last']} |"
        )
    (out_dir / "index.md").write_text("\n".join(index) + "\n")

    total_msgs = sum(r["messages"] for r in rows)
    total_words = sum(r["words"] for r in rows)
    print(f"wrote {len(rows)} project files to {out_dir}")
    print(f"total: {total_msgs} messages, {total_words} words")
    print(f"start with {out_dir}/index.md")


if __name__ == "__main__":
    main()
