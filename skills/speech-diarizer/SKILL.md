---
name: speech-diarizer
version: 0.3.0
description: Transcribes a local audio or video file into a speaker-labeled transcript using local WhisperX + pyannote diarization, and identifies recurring people by voice via an enrolled voiceprint store. Use when the user wants to know who said what - a transcript that separates speakers and names the ones it has met before (interviews, meetings, calls, podcasts).
---

# speech-diarizer

turn a local media file into a speaker-labeled transcript where each turn is attributed to a speaker (SPEAKER_00, SPEAKER_01, ...). this is the diarization-specialized counterpart to `speech-video-transcriber`: use this one whenever the recording has more than one voice and the user cares who said what.

the pipeline is fully local and runs well on apple silicon:

- transcribe with `faster-whisper` (via whisperx), default model `large-v3`, on cpu (ctranslate2 is cpu-only on macos)
- align to word-level timestamps
- diarize with `pyannote/speaker-diarization-3.1` (uses mps on apple silicon when available)
- assign speakers to words and write `.txt`, `.srt`, and `.json`

## self-contained scripts

- `scripts/diarize.py` - the engine. a PEP 723 inline-script declaring its own python (`>=3.10,<3.13`) and dependency (`whisperx>=3.3`), so `uv run --script` builds and caches an isolated environment automatically. nothing is installed into the repo's shared `.venv`.
- `scripts/enroll.py` - names speakers in the voiceprint store (PEP 723, depends only on `numpy`).
- `scripts/voiceprints.py` - shared store + cosine-matching module imported by both (not run directly).
- the enrolled voiceprint store is machine-global, not bundled with the skill. it lives at `~/.config/speech-diarizer/voiceprints.json` by default, so every copy of the scripts on this machine shares one set of voiceprints. override with `--store /path` or `$SPEECH_DIARIZER_VOICEPRINTS` (point it at an iCloud/synced path for cross-machine use).

## speaker identification (who, not just which)

diarization alone gives anonymous `SPEAKER_00/01/02` labels that mean nothing across recordings. this skill adds identification: pyannote already emits a voice embedding ("voiceprint") per speaker, and the skill matches those against an enrolled store by cosine similarity.

the flow is learn-as-you-go:

1. run `diarize.py` - it caches each speaker's embedding to `~/.cache/speech-diarizer/`, and auto-labels any speaker matching an enrolled voiceprint above `--threshold`. unmatched speakers stay `SPEAKER_XX` (and the `.md` frontmatter lists them as unrecognized).
2. read the `.md`, recognize an unknown speaker, and enroll them once with `enroll.py <run-stem> SPEAKER_XX=Name`.
3. every future recording auto-resolves that person. enrolling the same person from more recordings sharpens their voiceprint (embeddings are averaged into a centroid).

constraints:

- embeddings only compare within ONE diarization model. the store records its model on first enroll and refuses to mix; always run with the same `--diarization-model` (default `pyannote/speaker-diarization-3.1`).
- default threshold is `0.5`. observed margins are wide (a person matches their own voiceprint near `1.0` while different speakers score near `0`), so `0.5` is safe; raise it if you ever see a false match, lower it if a known person is missed.

## when to use it

use this skill when the user wants any of the following:

- a transcript that distinguishes multiple speakers
- "who said what" from an interview, meeting, call, or podcast
- speaker-attributed quotes for later analysis or coaching
- subtitles (`.srt`) with speaker tags

if the recording is a single speaker, prefer `speech-video-transcriber` - it is lighter and faster. use this skill specifically when speaker separation matters.

## required setup

- `ffmpeg` on PATH (whisperx uses it to load audio)
- `uv` (the script runs via `uv run --script`; deps install on first run)
- huggingface auth, resolved in this order: `--hf-token` flag, then `$HF_TOKEN`, then the cached `hf auth login` token (`~/.cache/huggingface/token`). being logged in via the cli is enough - no `.env` entry required.
- accepted licenses for the two gated pyannote models (one-time, free), on the logged-in account:
  - https://hf.co/pyannote/speaker-diarization-3.1
  - https://hf.co/pyannote/segmentation-3.0

if not logged in, run `hf auth login` once, or add `export HF_TOKEN=hf_...` to `ai-agents-config/.env` and `source .env` before running.

## workflow

1. resolve the media path to an absolute path before running anything
2. if the user knows the speaker count, pass `--num-speakers` (or `--min-speakers`/`--max-speakers`) - this sharply improves accuracy
3. if the user gives a language hint, pass `--language`
4. run the script (the diarization step is the slow part; large-v3 on cpu is fine on m-series but not instant)
5. return the output paths, and optionally relabel `SPEAKER_00/01/...` with real names from the `.txt` if the user identifies them

## command

the first invocation resolves and caches the environment, so it takes longer; later runs are fast to start.

```bash
cd /Users/rami/Documents/life-os/ai-agents-config/skills
uv run --script speech-diarizer/scripts/diarize.py "/absolute/path/to/recording.m4a"
```

common options:

```bash
# known number of speakers (most accurate)
uv run --script speech-diarizer/scripts/diarize.py \
  "/absolute/path/to/call.m4a" \
  --num-speakers 3 --language en

# bound the speaker count when exact number is unknown
uv run --script speech-diarizer/scripts/diarize.py \
  "/absolute/path/to/meeting.mp4" \
  --min-speakers 2 --max-speakers 5

# write outputs to a chosen directory (default: ~/Documents/transcriptions)
uv run --script speech-diarizer/scripts/diarize.py \
  "/absolute/path/to/interview.wav" \
  --num-speakers 2 \
  -o "/absolute/path/to/transcripts"

# multiple files in one run
uv run --script speech-diarizer/scripts/diarize.py a.m4a b.m4a c.wav --num-speakers 2

# faster, lower-accuracy pass for a quick check
uv run --script speech-diarizer/scripts/diarize.py \
  "/absolute/path/to/recording.m4a" --model small
```

## enrolling speakers

after a run, name the speakers you recognize so they auto-resolve next time. reference the raw `SPEAKER_XX` labels (visible in the run's stderr summary and the sidecar):

```bash
cd /Users/rami/Documents/life-os/ai-agents-config/skills

# enroll by run stem - enroll.py finds the cached embeddings automatically
uv run --script speech-diarizer/scripts/enroll.py call SPEAKER_00=Rami "SPEAKER_01=Full Name"

# (also accepts a full base path or the .voiceprints.json directly)

# add another sample for someone already enrolled (just enroll again from a new run)
uv run --script speech-diarizer/scripts/enroll.py another-call SPEAKER_02=Rami

# inspect or prune the store
uv run --script speech-diarizer/scripts/enroll.py --list
uv run --script speech-diarizer/scripts/enroll.py --remove Keith
```

## options

- `audio` - one or more media files (positional; wav, mp3, m4a, mp4, etc.)
- `--num-speakers N` - exact speaker count if known (best accuracy)
- `--min-speakers N` / `--max-speakers N` - bound the count when exact is unknown
- `--model` - whisper size, default `large-v3` (try `small` or `medium` for speed)
- `--language` - language code like `en` (default: auto-detect)
- `--diarization-model` - pyannote pipeline (default `pyannote/speaker-diarization-3.1`; try `pyannote/speaker-diarization-community-1` if whisperx ships pyannote.audio>=4)
- `--batch-size` - transcription batch size (default 8)
- `--hf-token` - token override (default `$HF_TOKEN`)
- `-o` / `--output-dir` - output directory (default: `$SPEECH_DIARIZER_OUTPUT_DIR` or `~/Documents/transcriptions`)
- `--threshold` - cosine similarity needed to attach an enrolled name (default `0.5`)
- `--no-identify` - skip voiceprint matching entirely (always anonymous `SPEAKER_XX`)
- `--store` - voiceprint store path (default `$SPEECH_DIARIZER_VOICEPRINTS` or `~/.config/speech-diarizer/voiceprints.json`); `enroll.py` takes the same flag

## output contract

the deliverable is ONE clean file. for each input the script writes, into the output dir (`-o`, else `$SPEECH_DIARIZER_OUTPUT_DIR`, else `~/Documents/transcriptions`):

- `<name>.md` - the primary output. yaml frontmatter (source, generated, duration, language, speakers, models) followed by speaker-labeled turns: `**[mm:ss] <speaker>:** text`, consecutive same-speaker segments merged. `<speaker>` is the enrolled name when identified, else `SPEAKER_XX`. readable by both a person and an ai tool, and the frontmatter `speakers` list flags who still needs enrolling. this is the only file written by default.

extras, only when asked:

- `--srt` -> `<name>.srt` subtitles with `[<speaker>]` tags
- `--json` -> `<name>.json` full whisperx result (word-level timing + speakers) for programmatic use

machinery, never in the output dir:

- per-run speaker embeddings are cached at `~/.cache/speech-diarizer/<name>.voiceprints.json` for later enrollment. you don't manage these - `enroll.py` reads them by run stem.

the script overwrites files of the same name. write to a fresh `-o` dir to preserve prior runs.

### timestamps per sentence

the `.md` merges a speaker's turn into one block with one timestamp. when you need to point at exact moments (a quote, a joke, a note about a line), run with `--json` and then:

```bash
uv run --script speech-diarizer/scripts/sentences.py /path/to/out/<name>.json
```

it prints one `[mm:ss] SPEAKER: sentence` line per sentence (`--no-speakers` drops the label). runs whisper left unpunctuated stay as one line; split them by word timing from the `.json` if needed.

## failure handling

- if no token is found (`HF_TOKEN` unset and no `--hf-token`), the script exits with setup instructions. try `source .env` first.
- if a gated model returns 401/403, the script detects it and tells the user the model gate hasn't been accepted on that account (links above)
- if `ffmpeg` is missing, whisperx audio loading fails - install it (`brew install ffmpeg`)
- do not paraphrase the transcript in place of the output files
