# Design

This workspace holds every visual Rami makes outside of video editing:
YouTube thumbnails, posters, things for his communities, and the face
library they share. Start with `AGENTS.md`: it explains the layout and the
conventions.

The skill definitions remain canonical in `ai-agents-config/skills/`. The
workspace receives symlinks, so every supported agent reads the same skill
files.

Included skills:

- `face-variations`: new photos of a person from their reference photos, with
  a chosen expression, pose and backdrop (Codex built-in image tool)
- `youtube-thumbnail`: the promise, the title, the thumbnail that completes it,
  and a check at the sizes YouTube shows
- `rami-voice`: titles and copy in Rami's own words

Do not put working files inside the hidden agent skill directories.
