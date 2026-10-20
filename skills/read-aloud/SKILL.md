---
name: read-aloud
description: Turn a web page, document, or pasted text (or chosen chapters or sections of it) into one natural-sounding narrated MP3, read by a local neural voice (Kokoro) instead of a robotic system voice. Saves to ~/Downloads by default. Manual only, run with /read-aloud; it does not trigger itself.
disable-model-invocation: true
compatibility: >-
  Needs uv and ffmpeg on PATH. The voice runs locally (Kokoro-82M, downloaded
  from Hugging Face on first run). The spot-check step uses mlx-whisper, so it
  needs Apple Silicon.
---

# read-aloud

Make an audiobook-style MP3 from any text. The pipeline is: extract the text, clean it for the ear, narrate a short sample, narrate the full script, then spot-check the result with speech-to-text.

All scripts are in `scripts/` next to this file. Each one is a self-contained `uv` script, so run them with `uv run <path>`. No install step is needed.

## Arguments

Read these from the user's message. Ask only when the source is missing.

- **source** (required): a URL, a local file (`.html`, `.txt`, `.md`, `.pdf`), or pasted text.
- **sections**: which part to read, for example "chapters 2 and 3" or a `#anchor` in the URL. Default: the whole document. Two or more sections become one file, in the order the user gives.
- **voice**: default `af_heart`. See [Voices](#voices).
- **output**: default `~/Downloads/<Document title> - <sections>.mp3`. Never overwrite an existing file. Add ` (2)` to the name instead.

## Steps

### 1. Work directory

Make a new empty directory for this run, for example `mktemp -d -t read-aloud`. Keep downloads and text files there, not in the skill folder.

### 2. Extract

- **URL or HTML file:** run `uv run scripts/extract.py <src> --list-anchors`. It prints every anchor (`id` or `name`) with its heading text. Choose the start anchor of the first section you want, and the anchor of the section that comes right after the last section you want. A `#fragment` in the user's URL is a start anchor. Then:

  ```bash
  uv run scripts/extract.py <src> --start <ANCHOR> --end <NEXT_ANCHOR> -o source.txt
  ```

  If the sections are not next to each other, run it once per range (`-o part1.txt`, `-o part2.txt`) and join the files with a `[pause 2]` paragraph between them.
  If the page has no useful anchors, extract the whole page and cut the text with the headings as markers.
- **PDF:** extract the text with `pdftotext -layout` (or the `pdf` skill), then join lines that were broken in the middle of a paragraph.
- **Markdown or plain text:** remove markdown syntax (`#`, `*`, links, images, code fences). Keep one paragraph per block, with a blank line between blocks.
- **Pasted text:** write it to `source.txt`.

Check the result: the word count, the first and last few lines, and that the section titles are present. Do not paste the document into the chat.

### 3. Clean for the ear

```bash
uv run scripts/clean.py source.txt -o narration.txt
```

This removes footnote markers like `[12]` and leading paragraph numbers (`--keep-numbers` keeps them). It changes ALL CAPS headings to title case, and puts a period after short headings so that the voice pauses. `--title "Chapter Two."` adds a first line if the extract does not include the title.

Then fix the text by hand, because a listener cannot see brackets or abbreviations. Look at:

- `awk 'NF && length($0) < 110' narration.txt`: the headings. Every chapter title must be there. Put a `[pause 2]` paragraph before each new chapter after the first one.
- `grep -o '([^)]*)' narration.txt | sort | uniq -c`: citations and asides. Write them as speech, for example `(cf. Gen 1:26-27)` becomes `(see Genesis, chapter 1, verses 26 to 27)`. Remove a pure reference (for example `(1948)`) only when it is noise.
- Abbreviations (`cf.`, `e.g.`, `i.e.`, `n.`, `nos.`, `St.`), URLs, `x:y` number pairs, Roman numerals after names (`Leo XIV` becomes `Leo the Fourteenth`), and symbols such as `%` and `&`.
- Typos from the source, for example a letter split from its word (`R esponsibility`).

Make these edits in `narration.txt` with sed or the Edit tool. Do not change the wording of the author.

### 4. Sample

```bash
uv run scripts/narrate.py narration.txt -o sample.mp3 --limit 3
uv run scripts/spotcheck.py sample.mp3 --seconds 30
```

The first run downloads the model and spaCy data (about 1 minute). Compare the transcript with the text. If a word is misread, respell it phonetically in `narration.txt`, then make the sample again.

### 5. Full narration

Run this in the background. A Mac with Apple Silicon makes about 10 minutes of audio per minute.

```bash
uv run scripts/narrate.py narration.txt -o "<output>.mp3" --voice af_heart --speed 0.95 \
  --title "<Document> - <Sections>" --artist "<Author>"
```

The MP3 is loudness-normalized (-16 LUFS, the podcast standard) at 128 kbps, with title and artist tags.

### 6. Verify and report

```bash
uv run scripts/spotcheck.py "<output>.mp3"
```

This transcribes 40 seconds at the start, middle, and end. The words must match the source. Then delete the work directory, and tell the user:

- the output path, the duration, and the size
- the voice and speed
- what you changed in the text (numbers removed, citations spelled out, typos fixed)
- what you verified, and which words may still sound wrong

## Voices

The first letter of the voice name sets the accent: `a` is American English, `b` is British English. The speed range is 0.8 to 1.2. 0.95 suits long, dense text.

| voice | accent and voice |
|---|---|
| `af_heart` | American, female. The default |
| `af_bella` | American, female |
| `am_michael` | American, male |
| `am_fenrir` | American, male |
| `bf_emma` | British, female |
| `bm_george` | British, male |
| `bm_fable` | British, male |

The model has 54 voices in total (see `voices/` in the `hexgrad/Kokoro-82M` repo on Hugging Face). If the user is not sure which voice to use, make a 3-paragraph sample with two or three voices, and let the user choose.

## Limits

- Tested in English only. Kokoro also reads Spanish (`e`), French (`f`), Hindi (`h`), Italian (`i`), and Brazilian Portuguese (`p`) through espeak-ng, which is already installed with it. Japanese (`j`) and Mandarin (`z`) need `misaki[ja]` or `misaki[zh]` added to the dependencies of `narrate.py`. `clean.py` and the spot-check model are English only. Make a sample before a full run in another language.
- The voice does not know the meaning of the text, so the emphasis in rhetorical passages stays even. Headings get longer pauses only because they are short lines.
- Pages that build their text with JavaScript return little text to `extract.py`. In that case, save the page from a browser and give the HTML file.
