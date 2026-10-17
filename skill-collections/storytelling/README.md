# Storytelling

This workspace is the story bank of Rami's life and the home of his
storytelling craft: the course, the books (Storyworthy), and the daily
practice. Start with `AGENTS.md`: it explains the layout, the modes, and the
conventions. The rules shared with stand-up and rhymes are in
`../AGENTS.md`.

The skill definitions remain canonical in `ai-agents-config/skills/`. The
workspace receives symlinks through `setup_symlinks.sh`, so every supported
agent reads the same skill files.

Included skills:

- `obsidian-search`: find what Rami already wrote about a moment or a theme
- `thought-partner`: find what a story is really about
- `rami-voice`: preserve Rami's voice in drafts
- `speech-diarizer`: local, speaker-labeled transcripts of class recordings
- `speech-video-transcriber`: local transcripts of solo recordings

Do not put working files inside the hidden agent skill directories.
