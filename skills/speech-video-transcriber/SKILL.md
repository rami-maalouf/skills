---
name: speech-video-transcriber
version: 0.2.0
description: Transcribes a local video or audio file into a markdown transcript using Whisper or OpenAI cloud. Use when the user wants a transcript from a video, audio, or voice note.
---

# speech-video-transcriber

turn a local media file into a markdown transcript with minimal local compute.

the intended path is:

- extract compact mono audio with `ffmpeg`
- send that audio to OpenAI transcription
- write a markdown transcript into `../transcriptions/` relative to the `skills/` directory

for this repo, that means outputs land in:

- `/Users/rami/Documents/life-os/ai-agents-config/transcriptions/`

## when to use it

use this skill when the user wants any of the following from a local media file:

- a transcript from a speaking video
- a transcript from an audio file
- a markdown transcript saved to disk for later analysis
- a first pass before communication coaching, speaking feedback, vocabulary analysis, or camera-performance review

if the user asks for speaking feedback but no transcript exists yet, use this skill first so later steps can work from a clean markdown source.

## backends

**local (default when user mentions whisper or offline):**
- flag: `--local`
- model: `small` (uses `~/.cache/whisper/small.pt` — no download needed if already cached)
- no API key required
- whisper handles audio internally, no chunking needed

**cloud (default otherwise):**
- model: `gpt-4o-transcribe`
- requires `OPENAI_API_KEY`
- auto-chunks audio if file exceeds 24 MB upload limit
- only switch to `gpt-4o-mini-transcribe` if the user explicitly wants the cheaper model

## defaults

- default output folder: `ai-agents-config/transcriptions/`
- default preprocessing: mono mp3 at 16 kHz and 48 kbps

## required setup

from `/Users/rami/Documents/life-os/ai-agents-config/skills`:

```bash
uv pip install -r speech-video-transcriber/scripts/requirements.txt
```

the machine also needs:

- `ffmpeg`
- `OPENAI_API_KEY`

## workflow

1. resolve the media path to an absolute path before running anything
2. if the user gives a language hint, pass `--language`
3. if the file contains names, jargon, brand terms, or unusual words, pass a short `--prompt` with those tokens to improve recognition
4. run the script
5. return the markdown path you wrote

## command

**local (no API key):**
```bash
cd /Users/rami/Documents/life-os/ai-agents-config/skills
uv run python speech-video-transcriber/scripts/transcribe_video.py "/absolute/path/to/video.mov" --local
```

**cloud (OpenAI API):**
```bash
cd /Users/rami/Documents/life-os/ai-agents-config/skills
uv run python speech-video-transcriber/scripts/transcribe_video.py "/absolute/path/to/video.mov"
```

common options:

```bash
# local with language hint
uv run python speech-video-transcriber/scripts/transcribe_video.py \
  "/absolute/path/to/video.mov" \
  --local \
  --language en

# cloud with jargon hint
uv run python speech-video-transcriber/scripts/transcribe_video.py \
  "/absolute/path/to/video.mov" \
  --language en \
  --prompt "rami, chalant, purpose os, posthog" \
  --model gpt-4o-transcribe

# save to specific path
uv run python speech-video-transcriber/scripts/transcribe_video.py \
  "/absolute/path/to/video.mov" \
  --local \
  --output "/path/to/output.md"
```

# local with a timestamped "## segments" section (for paper edits / clip logging)
uv run python speech-video-transcriber/scripts/transcribe_video.py \
  "/absolute/path/to/video.mov" \
  --local \
  --segments
```

## output contract

the script writes one markdown file to the shared transcriptions directory and prints the final path.

the markdown includes:

- source media path
- generation timestamp
- model used
- optional language hint
- chunk count
- full transcript text
- with `--segments` (local only): a `## segments` section, one `[mm:ss] text` line per whisper segment

if a file with the same name already exists, the script appends a timestamp suffix instead of overwriting it.

## examples

**example 1**

user request:
`transcribe /Users/rami/Documents/life-os/speech/founder-story-take-01.mov`

run:

```bash
cd /Users/rami/Documents/life-os/ai-agents-config/skills
uv run python speech-video-transcriber/scripts/transcribe_video.py \
  "/Users/rami/Documents/life-os/speech/founder-story-take-01.mov"
```

**example 2**

user request:
`make a transcript of /Users/rami/Documents/life-os/speech/camera-practice/clarity.mp4 and keep the names right. the language is english.`

run:

```bash
cd /Users/rami/Documents/life-os/ai-agents-config/skills
uv run python speech-video-transcriber/scripts/transcribe_video.py \
  "/Users/rami/Documents/life-os/speech/camera-practice/clarity.mp4" \
  --language en \
  --prompt "rami, chalant, purpose os"
```

## failure handling

- if `OPENAI_API_KEY` is missing, try to run `source .env` to load it and if it still fails stop and ask for it
- if `ffmpeg` is missing, stop and report that dependency clearly
- if transcription fails on a chunk, surface the chunk number and the upstream error
- do not paraphrase the transcript in place of the output file
