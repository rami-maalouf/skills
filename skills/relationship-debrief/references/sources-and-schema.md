# sources and schema reference

read this when you need the exact shape of the input transcript, the speaker-attribution quirk, or the per-person note schema in the vault.

## 1. the input: openoats transcripts

calls land as markdown in `~/Documents/transcriptions/OpenOats/`, named `YYYY-MM-DD-HHMM-slug.md`. the file has three useful regions:

1. **frontmatter** - `title`, `date`, `duration`, `participants`, `recorder` (this is Rami), `engine`, `language`. the `participants` list is anonymous (`Speaker 1`, `You`, `Them`, `Speaker 2`, ...) and is not trustworthy for identity.
2. **auto-generated meeting notes** - `## Summary`, `## Key Points`, `## Action Items`, `## Decisions Made`, `## Open Questions`. this section is clean prose and it names real people ("John to host", "Rami and David to collaborate", "Speaker 1 (Dan) to handle production"). treat it as the rosetta stone for identity and for what actually happened.
3. **verbatim transcript** - under `## Transcript`, lines look like `[hh:mm:ss] **Speaker N:** text` or `[hh:mm:ss] **You:** text`.

## 2. the dual-channel artifact (the thing that breaks naive attribution)

openoats records two streams: the meeting audio (other people, labeled `Speaker N`) and Rami's local mic (labeled `You`). the streams bleed into each other, so the `You` channel frequently re-transcribes whatever a `Speaker N` just said, 1-4 seconds later, with slightly different words.

example from a real call:

```
[00:00:00] **Speaker 1:** I'd really like to get an active live stream program started. Rami is going to be a big part of that...
[00:00:03] **You:**       live stream program started. Rami is gonna be a big part of that...
```

the `You` turn here is an echo of Speaker 1, not Rami speaking. note also that Speaker 1 says "Rami is going to be a big part" - so Speaker 1 is not Rami either.

**reconciliation heuristics:**

- a `You` turn whose text substantially overlaps the adjacent `Speaker N` turn within a few seconds is an echo. attribute that content to the `Speaker N`, not to Rami.
- Rami's real turns are the `You` content that is *not* a near-duplicate of a neighbor (genuine questions, agreements, his own points).
- never assume `You` == Rami wholesale. when the channel is too tangled to separate confidently, say so in the report rather than inventing who said what.
- cross-check every identity claim against the meeting-notes section and the action items, which encode who is responsible for what.

## 3. resolving speakers to real names

- `You` maps to Rami only for his de-echoed turns.
- map each `Speaker N` to a real name using: names used in conversation ("thanks <name>", "<name>, what do you think"), the summary/action items, and the cast of his known team.
- before adopting a name, check `My Social Circle/` for an existing note so you use the canonical spelling and do not create a duplicate (a first name likely resolves to an existing full-name note). the roster of known people lives in the vault (`My Social Circle/`) and the voiceprint store - do not hardcode names here.
- always show the resulting speaker -> name map with a confidence note at the top of the report, so Rami can correct it. early calls will need correction; that is expected.

## 4. the vault relationship CRM (`My Social Circle/`)

full convention is in `<vault>/My Social Circle/CLAUDE.md`. the essentials:

- one markdown note per person, filename is their plain display name (`David.md`). work teammates use the tag `person/work`.
- the folder is **gitignored - there is no undo**. this is real data about real coworkers. do not overwrite or restructure existing notes. treat writes here as careful, additive, and only on explicit confirmation.
- the CRM is link-based. a person's `## Conversations` section is a dataview query `FROM [[]] AND #meeting` - it auto-populates from any `#meeting` note that links to them. so the way to "log a conversation" is to create a `#meeting` note that links the attendees, not to paste transcript text into the person note.
- open follow-ups become `#ref/convo` tasks mentioning the person's name - those surface under their `## Convo Topics`.
- two template variants coexist (a current bare-`person` variant and an older `person/family|friend|work` variant). when editing an existing note, match its variant; do not convert one to the other.

## 5. where outputs go

- **debrief report** (the artifact Rami reads): `<transcript_dir>/debriefs/<transcript-name>.md`. this is the default and is always safe to write.
- **proposed CRM updates**: included as a section inside the debrief report, written as ready-to-apply blocks. they are applied into `My Social Circle/` and `My Meetings/` only when Rami explicitly confirms, mirroring how `generate-principles` defaults to scratch and only touches the vault on request.
