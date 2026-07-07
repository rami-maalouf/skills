You are applying the approved CRM proposals from a relationship-debrief report into Rami's Obsidian vault. This is an explicit, user-initiated action - but the `My Social Circle/` folder is gitignored with no undo, so be careful and strictly ADDITIVE.

REPORT: {{REPORT}}

Read the report's "## Proposed CRM updates" section. The `#meeting` note was already written when the debrief ran - do NOT recreate or edit it. Apply only the per-person updates.

For each proposed person:

1. Resolve identity first. Look for an existing note at `My Social Circle/<Name>.md`, and check `My Social Circle/CLAUDE.md` for the schema and the two template variants. Resolve nicknames against existing notes (e.g. "Dan" -> existing "Dan Kelly.md" if present) so you never create a duplicate person.

2. If the note does NOT exist, create it from the proposal using the CURRENT bare-`person` template variant, tagged `person/work`, with a tight one-line `Summary`, `KeepInTouch: true`, and `LastChatted` set to the call date. Include a `### How to communicate with them` subsection under `## Details`.

3. If the note DOES exist, do not overwrite or restructure it. Match its existing variant and only ADD:
   - ensure a `### How to communicate with them` subsection exists under `## Details`; merge the proposal's communication guidance into it concisely - update and dedupe, never stack duplicate lines.
   - append one dated bullet under a `### Debrief notes` subsection: `- YYYY-MM-DD: <one-line observation> ([[<meeting note title>]])`.

4. Add the proposed `#ref/convo` follow-up tasks so they surface under the person's Convo Topics: append them to that person's note as `- [ ] <text including the person's name> #ref/convo` lines (under `## Convo Topics` if present, else a new one). Do not duplicate a task that is already there.

Rules:
- Additive only. Never delete or rewrite existing content in a person note.
- Preserve the link-based CRM: do not paste transcript text into person notes; reference the `#meeting` note instead.
- Headless - do not ask questions. If a proposal is too ambiguous to apply safely, skip it and report why.

End your final message with a concise ledger: CREATED (which notes), UPDATED (which notes + what you added), TASKS ADDED, and SKIPPED (with reason). Nothing else.
