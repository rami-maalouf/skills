---
name: relationship-debrief
description: Turn a call or meeting transcript into a relationship debrief - per-person observations about how each attendee communicates, what they value, where connection broke or landed, and how Rami can communicate better with them next time. Accumulates into the My Social Circle CRM over time. Use this whenever Rami points at a meeting transcript (especially OpenOats files in ~/Documents/transcriptions/OpenOats), finishes a call, or asks to debrief a conversation, reflect on how a discussion went, understand a teammate, prep for talking to someone, or get better with a specific person. Trigger it even when he just says "what did I learn about David from this" or "how did that call go" - this is the skill for relationship reflection, as opposed to communication-analysis which grades his own delivery.
---

# Relationship Debrief

Rami works with a small team and wants to get better at communicating with each specific person. The point of this skill is to make every call leave a trace: a clear read on each person, and a concrete way to show up better with them next time. Done repeatedly, these traces accumulate into a real understanding of each teammate in his `My Social Circle/` CRM.

This is the relational counterpart to `communication-analysis`. That skill grades how Rami spoke (vocab, clarity, persuasion). This skill is about the people on the other side and the relationship between them and Rami. Run both when he wants the full picture; run this one alone when he cares about the people, not his delivery.

## What you produce

1. **A debrief report** - the artifact Rami reads. Always written, always safe. Goes to `<transcript_dir>/debriefs/<transcript-name>.md`.
2. **Proposed CRM updates** - ready-to-apply blocks inside the report (durable observations per person, a meeting note, follow-up tasks). These touch the vault only when Rami confirms.

Default to writing only the report. Apply changes into `My Social Circle/` and `My Meetings/` solely when Rami explicitly asks. The vault folder is gitignored with no undo and holds real data about real coworkers - that asymmetry (a wrong auto-edit is unrecoverable, a proposal costs nothing) is why proposals are the default.

## The hard part: who actually said what

Read `references/sources-and-schema.md` before doing anything else. The input format (OpenOats) has a trap: it records two audio streams, and the `You` channel (Rami's mic) echoes other people's words a few seconds later. So `You` is not reliably Rami, and the anonymous `Speaker N` labels mean nothing across calls.

Getting attribution wrong poisons everything downstream - you would record observations about David that were actually Dan. So treat identity as an inference problem, not a given:

- Reconcile the dual-channel echoes (heuristics in the reference). Strip echoes before reading turns as anyone's real words.
- Use the clean auto-generated Summary / Action Items / Decisions as your source of truth for who did and said what - they name real people.
- Resolve each speaker to a real name. For work calls, read the private roster at `My Social Circle/Expo Team.md` (names, roles, relationship to Rami) first; also check `My Social Circle/` person notes for the canonical spelling so you do not create duplicates.
- When the channels are too tangled to separate a person's contribution confidently, say so in the report. An honest "attribution here is uncertain" is far more useful to Rami than confident fiction.

## Workflow

### 1. Read and reconcile
Read the transcript. Separate the clean meeting-notes region from the verbatim turns. De-echo the `You` channel. Build a working model of who was present and what each person actually contributed.

### 2. Resolve speakers to names
Produce a `Speaker N / You -> Name` map with a one-line confidence note and the evidence you used. This goes at the top of the report so Rami can correct it in seconds.

### 3. Extract per-person observations
For each non-Rami attendee, fill the card below. Density is the point: Rami should absorb a person in about ten seconds. Hard rules: one line per lens, roughly 12-20 words, a fragment or a single short sentence - never two. At most one short quoted fragment in the whole card, and only if it truly earns its place - this card is your distilled judgment, not an evidence dump (leave the quotes for the meeting note and the transcript). If you catch yourself writing a second sentence in a bullet, you are overrunning - cut to the conclusion. Drop any lens with no real signal rather than padding it; if two people behaved alike, note the contrast instead of repeating.

- **Style** - how they think and express, in a clause: direct/exploratory, big-picture/detail, fast/deliberate, data/intuition.
- **Cares about** - what moves them, what wins an argument with them.
- **With Rami** - rapport and any friction in one line: trust, deference, tension, where they talked past each other.
- **Next time** - the single most useful behavioral change, fused with what already worked ("lead with the headline, he loses patience with build-up"; "bring data, vibes do not move him"). Concrete and behavioral, never generic.
- **Threads** - open commitments; who owes whom what.

Anchor every line in something that actually happened (a paraphrase is fine given noisy attribution). A line with no basis is noise - delete it.

### 4. Reflect on how Rami showed up
A short relational self-read, distinct from delivery: did he listen or dominate, advocate or withdraw, build on others or steamroll, stay curious or get defensive. This is the reflection muscle the skill is meant to build.

### 5. Write the report, then propose CRM updates
Write the report using the template below. Then draft the CRM updates as apply-ready blocks. Do not write them into the vault unless Rami confirms.

## Report template

Use this structure. Keep it tight - dense and skimmable beats long.

```markdown
---
source: <path to transcript>
call: <title>
date: <date>
attendees: [<resolved names>]
generated: <today>
---

# Debrief: <call title>

## Who was on the call
<Speaker -> Name map, with a confidence note. Flag anyone uncertain.>

## TL;DR
<2-3 lines: what this call was, and the one relational headline.>

## Per person

### <Name>
- **Style:** ...
- **Cares about:** ...
- **With Rami:** ...
- **Next time:** ...
- **Threads:** ...

### <Name>
...

## How I showed up
<short relational self-reflection>

## Carry-forward
<per-person convo topics and commitments to raise next time>

## Proposed CRM updates (apply only on confirm)
<for each attendee, the durable lines to append to their My Social Circle note;
 a #meeting note for My Meetings/ that links attendees; any #ref/convo follow-up tasks.
 Mark clearly that these are proposals.>
```

## Pre-call prep mode

When Rami asks to prep for a call with someone (e.g. "I'm about to talk to <name>, what should I remember"), run in reverse: read that person's `My Social Circle/` note and recent debriefs, and surface their style, what works with them, open threads, and the one thing to do differently this time. Same intelligence, pointed forward instead of back - this is where the reflection actually changes behavior.

## Notes on judgment

- Be specific and honest. Rami uses this to act, so a sharp uncomfortable read beats a flattering vague one. If he came across badly, say it plainly and constructively.
- Do not invent rapport or conflict that is not in the call. Silence on a lens is fine.
- Keep transcript content out of person notes - the CRM is link-based by design (see reference). Log conversations as linked `#meeting` notes, not pasted text.
