---
name: letterly-process
version: 2.0.0
description: Turns Letterly magic rewrites fetched through the Letterly MCP into Obsidian markdown notes in unprocessed/, with Letterly tags and IDs in the frontmatter. Used by letterly-automation.
---

# Letterly Process

This script writes Obsidian notes from a batch folder that the agent fills with the Letterly MCP. The full steps are in the `letterly-automation` skill.

## Commands

```bash
# the created_after date for list_notes: newest Created in the vault minus 7 days
.venv/bin/python letterly-process/scripts/process.py window [--lookback-days 7]

# report which rewrites are new and need their full text
.venv/bin/python letterly-process/scripts/process.py import <batch_dir> --plan

# write the new notes into unprocessed/
.venv/bin/python letterly-process/scripts/process.py import <batch_dir>
```

Both commands take `--vault <path>` before the command name. Without it, the script finds the vault by its `.smart-env/` folder.

## Batch folder

- `manifest.json`: `{"notes": [{"note_id", "rewrite_id", "title", "created", "tags", "chars"}]}`. `created` is Letterly's epoch milliseconds. `chars` is the `Text: N chars total` value from `get_rewrite`.
- `<rewrite_id>.txt`: the full rewrite text.

## Rules the script applies

- **Duplicates:** a rewrite is skipped if a note in `unprocessed/` or `My Outputs/Transcriptions/` has the same `letterly_rewrite_id` or the same file name.
- **Text length:** the text, without whitespace at the start and end, must be within 2 characters of `chars`. If not, the note is not written.
- **File name:** the Letterly title without illegal characters. Untitled notes use the first 5 words of the text.

## Frontmatter

```yaml
tags:
  - note
letterly_tags:
  - "journal"
letterly_note_id: 3319344
letterly_rewrite_id: 1849140
Links:
Created: 2026-10-20T15:28:38
```

`letterly_tags` keeps the Letterly tags apart from the Obsidian `tags` field. Later AI metadata generation uses them as hints, and they do not become vault-wide Obsidian tags. `Created` is UTC with no offset.
