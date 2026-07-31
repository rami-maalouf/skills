---
name: vocal-remover
description: >-
  Separate a song into isolated vocals and instrumental audio through
  vocalremover.org using macOS Computer Use. Use this whenever Rami asks to
  remove vocals, isolate vocals, make karaoke or acapella tracks, split a song
  into vocals and music, or process a local audio file or YouTube URL through
  Vocal Remover. Use the site's Splitter tool instead when the user requests
  vocals, bass, drums, and other multi-stems.
compatibility: >-
  Requires macOS Computer Use, an installed browser, ffmpeg and ffprobe, and uv
  for downloading URL sources with yt-dlp.
---

# Vocal Remover

Turn one song into two verified audio files:

- `[song]-instrumental.[ext]`
- `[song]-vocals.[ext]`

Use Computer Use for every browser and macOS dialog interaction. Use terminal
commands only for local file preparation, download discovery, naming, moving,
conversion, and validation.

## Required setup

Before any UI action:

1. Read the complete `computer-use` skill available in the current environment.
2. Confirm that `ffmpeg` and `ffprobe` are on `PATH`.
3. Resolve the source, output directory, and requested output format.
4. Resolve every local path to an absolute path.

If Computer Use is unavailable, stop and explain that this skill cannot perform
the website workflow. Do not silently substitute Playwright, a browser plugin,
AppleScript, or coordinate-synthesis tools.

## Defaults

- Website: `https://vocalremover.org/`
- Browser: Brave Browser on Rami's current Mac
- Local-file output directory: beside the source
- URL-source output directory: `/Users/rami/Music/fav-songs`
- Output format: preserve the site's highest-quality downloaded format
- Naming: `<source-stem>-instrumental.<ext>` and
  `<source-stem>-vocals.<ext>`
- Existing outputs: preserve them and add a timestamp instead of overwriting

If the user requests M4A, download the site's highest-quality result first and
then convert losslessly sourced audio to AAC M4A with `ffmpeg`. Never label an
MP3 or WAV file as M4A by changing only its extension.

## Upload authorization

Uploading sends the selected audio to `vocalremover.org`.

Treat the upload as pre-approved only when the user explicitly:

- asks to use `vocalremover.org`
- asks to use the Vocal Remover skill
- asks to upload the named source to Vocal Remover

Otherwise, pause immediately before clicking the file dialog's `Open` button.
Name the exact local file and the destination website, then ask for
confirmation.

The user's authorization to upload one file does not authorize uploading other
files from the same directory.

## Source preparation

### Local file

1. Verify that the file exists and is a regular audio or video file.
2. Use `ffprobe` to confirm that it contains an audio stream.
3. Keep the original file untouched.
4. If the site rejects the container, create a temporary M4A upload copy with
   `ffmpeg` and leave the original unchanged.

### YouTube URL

Download one audio item, never a playlist:

```bash
uvx yt-dlp \
  --no-playlist \
  -f "bestaudio[ext=m4a]/bestaudio" \
  -x \
  --audio-format m4a \
  --audio-quality 0 \
  --embed-metadata \
  --embed-thumbnail \
  -o "/absolute/output/directory/%(title)s.%(ext)s" \
  "https://youtube.com/..."
```

If YouTube requires authentication, retry with the browser the user already
uses, such as `--cookies-from-browser brave`. Explain that macOS may request
Keychain access. Do not expose or persist browser cookies.

Verify the downloaded file with `ffprobe` before uploading it.

## Browser workflow

Brave Browser is installed and verified on Rami's current Mac. No additional
browser is required.

1. Start with `sky.get_app_state({ app: "com.brave.Browser" })`.
2. If Brave is unavailable, use `sky.list_apps()` and select an installed
   mainstream browser. Prefer Google Chrome, then Safari.
3. Open a new browser tab for this workflow.
4. Navigate to `https://vocalremover.org/` through the address bar.
5. Fetch fresh app state and locate `Browse my files` by accessibility text.
6. Click it and fetch fresh state for the macOS file dialog.
7. Press `super+shift+g`, enter the absolute source path, and press `Return`.
8. Confirm that the intended filename is selected.
9. Click `Open` only when the upload is authorized.
10. Fetch fresh app state after the upload and throughout processing.

Prefer current accessibility element indexes over screen coordinates. Element
indexes become stale after the UI changes, so inspect fresh state before every
decision.

## Processing and error states

Wait for the page to expose the separated vocal and music controls. Use short,
bounded waits only when the page is visibly processing, then inspect fresh
state.

Handle these states explicitly:

- `Too many requests from your IP address`: stop immediately, report the rate
  limit, and recommend retrying later. Do not loop, refresh repeatedly, change
  networks, or attempt to evade the limit.
- CAPTCHA: hand control to the user. Computer Use policy requires the user to
  complete it.
- Unsupported file or decoding error: create a temporary AAC M4A upload copy
  and retry once.
- Network or server error: retry once after a fresh state check, then stop with
  the exact visible error.
- Unexpected subscription or payment screen: stop. Do not start a trial,
  subscribe, or make a purchase.
- Missing one of the two tracks: do not claim success or synthesize a fake
  replacement.

## Download both stems

Before downloading, record the current filenames and modification times in the
browser's download directory. This makes new downloads unambiguous.

1. Keep both site mix controls at their separated defaults unless the user asks
   for a custom balance.
2. Download the instrumental or music track.
3. Fetch fresh app state and download the isolated vocal track.
4. Inspect the download directory and identify only files created after the
   recorded baseline.
5. Map each file to the button that produced it. Do not guess from filename
   alone.
6. Move the files into the requested output directory.
7. Rename them to the output contract without overwriting existing files.
8. Convert only when the user requested a different format.
9. Validate both final files with `ffprobe`.

For M4A conversion:

```bash
ffmpeg -i "/absolute/input.wav" \
  -map_metadata 0 \
  -c:a aac \
  -b:a 256k \
  "/absolute/output.m4a"
```

Do not delete the site's original downloads until both converted files pass
validation. Move redundant originals to Trash only when the user requested
cleanup.

## Success criteria

Finish only when:

- both instrumental and vocal files exist
- both contain a decodable audio stream
- both have non-zero duration
- filenames clearly identify the stems
- the original source is unchanged

Report:

- clickable absolute paths for both stems
- codec, container, duration, and size
- whether conversion occurred
- any site warning or quality limitation

## Multi-stem requests

When the user wants vocals, bass, drums, and other instruments, use
`https://vocalremover.org/splitter-ai` through the same Computer Use workflow.
Expect processing to take longer and verify every requested stem before
reporting completion.
