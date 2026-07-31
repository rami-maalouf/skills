# Skill Collections

Skill collections declare which canonical skills belong in each top-level
workspace under `/Users/rami/Documents/life-os/`.

Each collection is a directory containing:

- `skills.txt`: one canonical `skills/<name>/` directory per line
- `README.md`: an optional workspace guide

Run the collection-only installer after adding or changing a collection:

```bash
bash setup_symlinks.sh --collections-only
```

This mode leaves global agent settings untouched. It creates the matching
workspace and links each skill into:

- `.agents/skills/` for the shared agent skills convention
- `.agent/skills/` for Antigravity-compatible discovery
- `.claude/skills/` for Claude Code

The collection never owns a copy of a skill. Edit the canonical source under
`skills/`, then rerun the installer.
