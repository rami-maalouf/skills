---
name: morning-brief
description: Rami's 2-minute morning brief. Reads last night's and this morning's voice notes (Letterly) or typed plan, plus My Ignition Library v2 and My Morning Fire v2, and replies with today's locked main task, a personal why for each task, and his own words quoted word for word. Use when Rami runs /morning-brief or asks for his morning brief.
compatibility: >-
  Needs the letterly mcp for voice notes and uv for the quote check. Reads the
  Obsidian vault at ~/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian.
---

# morning brief

the morning half of rami's routine. the system lives in `~/Documents/life-os/routine/` (read its `AGENTS.md` once if you need the why). rami's own spec:

> "surface specific things from there, word for word. because ai is bad at paraphrasing."
> "giving me a personalized reminder of why i should care about the things i'm doing today, and why i should do it to the best of my abilities."

the output is a markdown reply. do not write it to the vault, the daily note, or any file.

## the three laws

1. **quotes are word for word.** every line under a quote heading is copied from a source and passes `scripts/verify_quotes.py`. if a quote fails, copy it again from the source. never reword it to make it pass. if it still fails, drop it.
2. **the night decides.** last night's main task is locked. do not re-plan, reorder, add, or judge tasks. do not suggest a better main task.
3. **two minutes.** the whole brief stays under 300 words. no preamble, no sign-off, no questions.

## step 1: gather the inputs

let `TODAY` be the local date (`date +%F`) and `YESTERDAY` the day before. let `WORK` be `$TMPDIR/morning-brief/$TODAY/` (create it).

1. **morning input.**
   - if rami typed text with the command, that text is the morning input.
   - otherwise call `letterly list_notes` with `created_after=YESTERDAY` and take the notes created today at or after 04:00 local time. `Created` is epoch milliseconds; convert with `date -r <seconds>`. call `get_note` for the full text of each.
   - if there is no morning input, the brief still runs from the night input alone.
2. **night input.** from the same list, take the notes created from YESTERDAY 18:00 to TODAY 04:00. call `get_note` for each. use the transcription, not a rewrite, as the quote source.
3. **the locked sentence.** look for the shutdown sentence ("tomorrow i ...") in this order: the night notes, the morning input, then `My Calendar/My Daily Notes/TODAY.md` and `YESTERDAY.md` in the vault. copy it word for word.
4. **the fire.** read these vault files in full:
   - `My Morning Fire v2.md`
   - `My Ignition Library v2.md`
   - `My Outputs/Transcriptions/Breaking the Cycle and Building Routines.md` (the note this routine was born from; its blessing paragraph is a valid source)
5. **connectors.** if a calendar or task tool (for example ticktick or google calendar) is available and authorized in this session, read today's items from it. if not, skip it silently.

save each voice note text to `WORK/` (for example `night-1.txt`, `morning-1.txt`, and `typed.txt` for typed input) so the quote check can read them.

## step 2: build the brief

- **tasks.** list only the tasks rami named (morning input, locked sentence, connectors). keep his order. keep his times. if he gave no time, show none. if he named no tasks, the today section is one line: `no tasks named yet. say them: what i want to do, what i have to do, and when.`
- **the why line.** one line per task, max 20 words, lowercase, in his voice. build it only from evidence: what he said about the task, who it serves, the bets in [[My Morning Fire v2]], his purpose (build useful things, form meaningful relationships). name the real person or stake when the evidence names one. no generic motivation ("you've got this", "crush it"). no invented stakes.
- **my words.** pick 3 to 5 quotes that fit today's tasks and today's mood. prefer the ignition library and morning fire; a line from last night's note is welcome when it hits. the quotes must be full phrases that stand alone. if rami sounds behind, low, or lousy, include one quote about blessings or people betting on him.
- **the blessing.** one quote, word for word, about what he has right now or the opportunities others never get.

## step 3: verify every quote

write every quote (the locked sentence, my words, the blessing) to `WORK/quotes.txt`, one per line, then run:

```bash
uv run ~/.agents/skills/morning-brief/scripts/verify_quotes.py "$WORK/quotes.txt" \
  --source "<vault>/My Morning Fire v2.md" \
  --source "<vault>/My Ignition Library v2.md" \
  --source "<vault>/My Outputs/Transcriptions/Breaking the Cycle and Building Routines.md" \
  --source "$WORK"/night-1.txt  # plus every other saved input file
```

the brief ships only when the check prints `N/N quotes verified`. a quote may be a contiguous slice of a longer source line; it may not merge two lines.

## step 4: reply with this shape

```markdown
# morning brief - <weekday> <month> <day>

## the one thing
> <locked sentence, word for word>

## today
- **<task>** <time if given> - <why line>

## my words
> <quote>
> - <source file or "last night's note">

## the blessing
> <quote>
```

if there was no locked sentence, replace the first section with:

```markdown
## the one thing
no sentence last night. say it now: tomorrow i [task] at [time]. done when [outcome]. starting with [first 10 minutes].
```

## what not to do

- no schedule proposals, no calendar edits, no task edits.
- no summaries of the voice notes.
- no new rituals, questions, or prompts.
- no writing to any file except the scratch files in `WORK/`.
