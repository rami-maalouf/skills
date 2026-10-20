---
name: letterly-automation
version: 2.0.0
description: Full Letterly pipeline - fetch new magic notes through the Letterly MCP, write them into Obsidian markdown, generate metadata, semantically link them, and move them to Transcriptions. Use when syncing or importing new Letterly magic notes.
compatibility: >-
  Needs the letterly mcp (https://mcp.letterly.app/mcp, authorized with /mcp) and the
  shared skills venv at ai-agents-config/skills/.venv. Obsidian must be running for
  Smart Connections to embed new notes before linking.
---

# Letterly Automation

Imports Rami's Letterly voice notes into the Obsidian vault. Only notes with a "Magic" rewrite are imported, and the note body is the magic rewrite text.

The agent owns judgment and the MCP calls. The scripts own structure.

- Only an agent can call the Letterly MCP, so the agent fetches the notes and writes them to a batch folder.
- `letterly-process` turns the batch into notes in `unprocessed/`. It checks the sync window, duplicates, and the text length.
- `generate-metadata` is agent work. No script calls an AI API.
- `workflow.py finish` validates the metadata, links the notes, and delivers them.

## Workflow

Let `SKILLS` be `/Users/rami/Documents/life-os/ai-agents-config/skills`, `PY` be `$SKILLS/.venv/bin/python`, and `WORK` be a new empty folder such as `$TMPDIR/letterly-sync/<timestamp>/`.

### 1. Get the sync window

```bash
$PY $SKILLS/letterly-automation/scripts/workflow.py window
```

It prints `{"created_after": "YYYY-MM-DD", ...}`: the newest `Created` date in `unprocessed/` and `My Outputs/Transcriptions/`, minus 7 days. The overlap catches magic rewrites that Rami made some days after he recorded the note. Duplicates are skipped later, so the overlap is safe. To backfill, use an earlier date.

### 2. List the notes (Letterly MCP)

Call `list_notes` with `created_after=<date>` and `page_size=100`. Read every page (the header shows `Page N/M`).

From each note, record:

- `note_id`: the number after `Note #`
- `title`: the text after the ID
- `created`: the `Created:` value (epoch milliseconds, UTC). Copy it as is.
- `tags`: the `title='...'` value of each tag, in order. Use `[]` when the note has no `Tags:` line.
- `rewrite_id`: from the rewrite line whose type contains `Magic`, for example `- [#1849140] PL#Magic | Status: processed`. Skip notes with no magic rewrite.

Write `WORK/manifest.json`:

```json
{"notes": [
  {"note_id": 3319344, "rewrite_id": 1849140, "title": "A Dream About My Mom's Car Crash and Health Fears",
   "created": 1792510118000, "tags": ["journal", "dreams", "family"]}
]}
```

### 3. Find which rewrites are new

```bash
$PY $SKILLS/letterly-automation/scripts/workflow.py import "$WORK" --plan
```

It prints `skipped:` for rewrites already in the vault (matched by `letterly_rewrite_id`, or by file name for notes imported before the IDs existed) and `needs text:` for the new ones. Fetch text only for the `needs text:` lines.

### 4. Fetch the full text (Letterly MCP)

For each new rewrite, call `get_rewrite(note_id, rewrite_id)`. The previews from `list_notes` are cut short, so never use them as the note text.

- The header shows `Text: N chars total`. Add `"chars": N` to that entry in `manifest.json`.
- If the header shows `Next chunk`, call again with that `offset` until you have all the text.
- Write the text after `Content:` to `WORK/<rewrite_id>.txt`. Remove the 4-space indent at the start of the first line. Do not change anything else: keep every word, quote mark, line break, and list number.

### 5. Import into `unprocessed/`

```bash
$PY $SKILLS/letterly-automation/scripts/workflow.py import "$WORK"
```

The script compares each text length with `chars`. If a text is more than 2 characters off, the script prints `failed:` and does not write that note. Fetch the text again and copy it exactly. Do not edit the text to make the count pass.

At the end, the script lists every note in `unprocessed/` that has no valid metadata.

### 6. Generate metadata

Run the `generate-metadata` skill on the listed files.

### 7. Validate, link, and deliver

```bash
$PY $SKILLS/letterly-automation/scripts/workflow.py finish
```

1. Validates the metadata of every note in `unprocessed/`.
2. Waits up to 90 seconds for Smart Connections to embed the valid notes. If Obsidian is closed, the wait times out and those notes get no `## Related Notes`.
3. Runs `obsidian-semantic-linker` on the valid notes.
4. Moves the valid notes to `My Outputs/Transcriptions/`. Notes without valid metadata stay in `unprocessed/`.

Report what was created, skipped, failed, and moved.

## Note format

```yaml
---
Status: 🎙️
tags:
  - note
letterly_tags:
  - "journal"
letterly_note_id: 3319344
letterly_rewrite_id: 1849140
Links:
Created: 2026-10-20T15:28:38
---
```

`Created` is the UTC time of the original voice note, without an offset. This matches the older notes from the CSV export.

## Troubleshooting

- **No Letterly tools:** the MCP is not authorized. Run `/mcp` in an interactive session and authorize `letterly`.
- **`needs text` after import:** a `<rewrite_id>.txt` file is missing in `WORK`.
- **`failed: text has N chars`:** the copied text is not the same as the Letterly text. Copy it again from `get_rewrite`.
- **No related notes:** Obsidian was closed, so Smart Connections did not embed the new notes. Open Obsidian, wait for indexing, then run `obsidian-semantic-linker` on the notes.
- **Metadata missing:** notes without valid generated metadata stay in `unprocessed/` instead of moving to `My Outputs/Transcriptions/`.
