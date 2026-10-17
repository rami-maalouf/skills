# Music Creation and Poems

This workspace is for writing rhymes, rap verses, songs, and poems over
instrumentals, with an agent as a writing partner. Start with `AGENTS.md`: it
explains the layout, the three writing modes, and the conventions.

The skill definitions remain canonical in `ai-agents-config/skills/`. The
workspace receives symlinks through `setup_symlinks.sh`, so every supported
agent reads the same skill files.

Included skills:

- `vocal-remover`: create instrumental and vocal stems through
  vocalremover.org
- `speech-video-transcriber`: transcribe a vocal stem locally to get a
  reference song's lyrics
- `thought-partner`: discover original angles, concepts, and creative tension
- `rami-voice`: preserve Rami's voice while developing written work
- `obsidian-search`: retrieve related ideas, lyrics, poems, and notes from the
  vault

Lyrics live in the vault (`My Outputs/My Poems/`), reached through the
`lyrics/` symlink. Do not put working files inside the hidden agent skill
directories.
