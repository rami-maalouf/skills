You are running an unattended post-call debrief on a single meeting transcript. Produce ONE synthesized debrief report. This runs headless with no human in the loop, so never ask questions - make your best judgment and flag uncertainty directly in the output.

TRANSCRIPT: {{TRANSCRIPT}}

Apply three skills by reading each SKILL.md and following it (read a skill before you use it):

1. Relationship debrief (the backbone): /Users/rami/Documents/life-os/ai-agents-config/skills/relationship-debrief/SKILL.md
2. Communication analysis (Rami's delivery): /Users/rami/Documents/life-os/ai-agents-config/skills/communication-analysis/SKILL.md
3. Co-CEO (strategy pressure-test): /Users/rami/Documents/life-os/ai-agents-config/skills/co-ceo/SKILL.md

Steps:

A. Run the relationship-debrief skill on the transcript. This is the body of the report. Honor its handling of the dual-channel speaker-attribution problem: reconcile the echoed `You` channel before attributing anyone's words, resolve speakers to real names with a confidence note, and check `My Social Circle/` for canonical name spellings so you do not create duplicates.

B. CRM writes - HYBRID policy:
   - AUTO-WRITE the factual #meeting note to the vault at `My Meetings/<call title>.md`. Use the meeting-note shape described in the relationship-debrief reference: frontmatter with `tags: [meeting]`, `Attendees` as `[[Name]]` links, a `Summary`, `MeetingDate`; a short `## Notes` section; and `## Action Items`. Include a one-line speaker-confidence caveat in the note body and a link back to the debrief report. This is a low-risk factual log, so writing it automatically is intended.
   - DO NOT create or edit any `My Social Circle/` person notes. Keep all per-person observations as apply-ready PROPOSALS inside the debrief report.

C. Communication coaching - this is what Rami most wants to improve, so make it genuinely detailed, not a few bullets. Extract Rami's genuine, de-echoed turns (his real `You` content, not echoes of other speakers) into a temp file beside the report, then run communication-analysis on that file per its skill (run its `scripts/analyze_file.py` to get the structured findings; that pass is deterministic/keyword-based, so layer real judgment on top of it). Write a substantive `## Communication coaching` section using the skill's full framework:
   - **Style diagnosis** - 2-3 lines naming how Rami communicated on this call: his register, his default moves, his tells.
   - **Highest-leverage fixes** - the habits costing him most, as many as the material genuinely supports. For each: quote his actual line, name the habit (hedging / asking permission before stating an idea / vague nouns where precise ones exist / sentences that collapse mid-thought / filler / unclear questions / talk-vs-listen balance), and say why it weakened the point.
   - **Sentence upgrade lab** - take 2-4 of his real sentences and rewrite each tighter and more direct, so he can hear the difference.
   - **Vocabulary / filler patterns** - recurring crutch words or vague phrasings, each with a sharper replacement.
   - **Keep doing** - his genuine strengths this call (a clean declarative that landed, a well-placed question), so he reinforces them.
   Link the full analysis artifact. If `analyze_file.py` cannot run (e.g. missing venv), produce the section from the skill's framework anyway. Be honest about the ceiling: this can only be as detailed as how much Rami actually spoke - if his turns were sparse, say so plainly rather than padding.

D. Strategy pressure-test - apply the co-ceo lens to the actual decisions and plans discussed. Add a `## Strategy pressure-test` section with the sharpest 2-4 challenges, risks, or blind spots. If the call had no real decisions worth pressure-testing, say that in one line instead of manufacturing critique.

E. Assemble ONE report at `<transcript_dir>/debriefs/<transcript-name>.md`. Order: the full relationship-debrief report as the body, then `## Communication coaching` (C) and `## Strategy pressure-test` (D), then the relationship-debrief's `## Proposed CRM updates` section last. In the proposals section, note that the #meeting note was already written and only the person-note edits await confirmation.

Constraints:
- Write only these: the one combined report, the one #meeting note, the communication-analysis artifact, and the temp file of Rami's turns. Touch nothing else in the vault.
- Be specific and honest. A sharp, uncomfortable read is more useful to Rami than a flattering vague one. If he came across poorly, say so constructively.
- Do not ask anything; this is headless.
- End your final message with exactly one line: `REPORT_PATH: <absolute path to the report>`
