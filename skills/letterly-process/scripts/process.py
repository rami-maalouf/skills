"""turn letterly magic rewrites fetched through the letterly mcp into obsidian notes.

the agent owns fetching (only an agent can call the mcp). this script owns structure:
the sync window, duplicate checks, the text length check, and the note format.

batch dir layout (written by the agent):
  manifest.json      {"notes": [{"note_id", "rewrite_id", "title", "created", "tags", "chars"}]}
  <rewrite_id>.txt   the full rewrite text, exactly as letterly returned it
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

LOOKBACK_DAYS = 7
# leading and trailing whitespace may differ from letterly's count, nothing else may
LENGTH_TOLERANCE = 2
CREATED_RE = re.compile(r"^Created:\s*(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})", re.MULTILINE)
REWRITE_ID_RE = re.compile(r"^letterly_rewrite_id:\s*(\d+)", re.MULTILINE)


def get_vault_root():
    candidates = [
        os.getcwd(),
        "/Users/rami/Documents/life-os/Obsidian",
        "/Users/rami/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian",
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, ".smart-env")):
            return c
    return os.getcwd()


def note_dirs(vault_root):
    return [
        os.path.join(vault_root, "unprocessed"),
        os.path.join(vault_root, "My Outputs/Transcriptions"),
    ]


def read_frontmatter(path):
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read(4000)
    except OSError:
        return ""
    if not text.startswith("---"):
        return ""
    end = text.find("\n---", 3)
    return text[:end] if end != -1 else ""


def scan_vault(vault_root):
    """return (newest created datetime, known rewrite ids, known file names)."""
    newest = None
    rewrite_ids = set()
    filenames = set()
    for directory in note_dirs(vault_root):
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not name.endswith(".md"):
                continue
            filenames.add(name)
            frontmatter = read_frontmatter(os.path.join(directory, name))
            created = CREATED_RE.search(frontmatter)
            if created:
                value = datetime.fromisoformat(created.group(1))
                if newest is None or value > newest:
                    newest = value
            rewrite_id = REWRITE_ID_RE.search(frontmatter)
            if rewrite_id:
                rewrite_ids.add(int(rewrite_id.group(1)))
    return newest, rewrite_ids, filenames


def sanitize_filename(name):
    """removes characters that are illegal in file names."""
    sanitized = re.sub(r'[\/*?:"<>|]', "", name)
    return sanitized.strip()[:200]


def note_filename(item, text):
    title = str(item.get("title") or "").strip()
    if not title or title == "Untitled":
        title = " ".join(text.split()[:5]) or "Untitled Note"
    return sanitize_filename(title) + ".md"


def created_iso(created_ms):
    # letterly timestamps are utc epoch ms; the vault stores utc without an offset
    return datetime.fromtimestamp(int(created_ms) / 1000, timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def yaml_scalar(value):
    return json.dumps(str(value), ensure_ascii=False)


def yaml_list(field, values):
    if not values:
        return f"{field}: []"
    lines = [f"{field}:"]
    for value in values:
        lines.append(f"  - {yaml_scalar(value)}")
    return "\n".join(lines)


def clean_tags(tags):
    result = []
    for tag in tags or []:
        tag = str(tag).strip().removeprefix("#").strip()
        if tag and tag not in result:
            result.append(tag)
    return result


def build_note(item, text):
    return f"""---
Status: 🎙️
tags:
  - note
{yaml_list("letterly_tags", clean_tags(item.get("tags")))}
letterly_note_id: {int(item["note_id"])}
letterly_rewrite_id: {int(item["rewrite_id"])}
Links:
Created: {created_iso(item["created"])}
---

{text}
"""


def load_manifest(batch_dir):
    with open(os.path.join(batch_dir, "manifest.json"), encoding="utf-8") as f:
        notes = json.load(f).get("notes", [])
    for item in notes:
        missing = [key for key in ("note_id", "rewrite_id", "title", "created") if key not in item]
        if missing:
            raise ValueError(f"manifest entry {item} is missing {', '.join(missing)}")
    return notes


def read_text(batch_dir, item):
    path = os.path.join(batch_dir, f"{int(item['rewrite_id'])}.txt")
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def check_length(item, text):
    expected = item.get("chars")
    if expected is None:
        return "manifest has no chars value from get_rewrite"
    actual = len(text.strip())
    if abs(actual - int(expected)) > LENGTH_TOLERANCE:
        return f"text has {actual} chars but letterly reports {expected}"
    return None


def command_window(args):
    vault_root = args.vault or get_vault_root()
    newest, _, _ = scan_vault(vault_root)
    if newest is None:
        print("no Created dates found in the vault. pass an explicit date to list_notes.", file=sys.stderr)
        return 1
    since = (newest - timedelta(days=args.lookback_days)).date().isoformat()
    print(json.dumps({"created_after": since, "newest_note": newest.isoformat()}))
    return 0


def command_import(args):
    vault_root = args.vault or get_vault_root()
    batch_dir = args.batch_dir
    unprocessed_dir = os.path.join(vault_root, "unprocessed")
    os.makedirs(unprocessed_dir, exist_ok=True)

    _, known_ids, known_files = scan_vault(vault_root)
    notes = load_manifest(batch_dir)

    created, skipped, needs_text, failed = [], [], [], []
    for item in notes:
        rewrite_id = int(item["rewrite_id"])
        title = str(item.get("title") or "")
        if rewrite_id in known_ids:
            skipped.append(f"{title} (rewrite {rewrite_id} already in vault)")
            continue

        # titles are known before the text, so the file name check can run in plan mode too
        title_filename = note_filename(item, "") if title and title != "Untitled" else None
        if title_filename and title_filename in known_files:
            skipped.append(f"{title} (file name already in vault)")
            continue

        text = read_text(batch_dir, item)
        if text is None:
            needs_text.append(item)
            continue
        if args.plan:
            continue

        error = check_length(item, text)
        if error:
            failed.append(f"{title}: {error}")
            continue

        filename = note_filename(item, text)
        if filename in known_files:
            skipped.append(f"{title} (file name already in vault)")
            continue

        with open(os.path.join(unprocessed_dir, filename), "w", encoding="utf-8") as f:
            f.write(build_note(item, text.strip()))
        known_files.add(filename)
        created.append(f"unprocessed/{filename}")

    for line in skipped:
        print(f"skipped: {line}")
    for item in needs_text:
        print(f"needs text: note {int(item['note_id'])} rewrite {int(item['rewrite_id'])} - {item.get('title')}")
    for path in created:
        print(f"created: {path}")
    for line in failed:
        print(f"failed: {line}")
    print(
        f"summary: created {len(created)}, skipped {len(skipped)}, "
        f"needs text {len(needs_text)}, failed {len(failed)}"
    )
    return 1 if failed or (needs_text and not args.plan) else 0


def build_parser():
    parser = argparse.ArgumentParser(description="import letterly magic rewrites into the vault")
    parser.add_argument("--vault", help="vault root; detected from .smart-env/ when omitted")
    sub = parser.add_subparsers(dest="command", required=True)

    window = sub.add_parser("window", help="print the created_after date for list_notes")
    window.add_argument("--lookback-days", type=int, default=LOOKBACK_DAYS)
    window.set_defaults(func=command_window)

    imp = sub.add_parser("import", help="write new notes from a batch dir into unprocessed/")
    imp.add_argument("batch_dir")
    imp.add_argument("--plan", action="store_true", help="only report which rewrites still need their text")
    imp.set_defaults(func=command_import)
    return parser


if __name__ == "__main__":
    parsed = build_parser().parse_args()
    sys.exit(parsed.func(parsed))
