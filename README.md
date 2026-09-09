# skills

Rami's collection of Agent skills, plus the agent config (Claude Code, Codex,
Gemini) that ties them together. Each skill is a self-contained directory with a
`SKILL.md` that tells an agent when and how to use it, and an optional `scripts/`
folder with the code it runs.

Most of these skills are built around Rami's own tools and context (his Obsidian
vault, his Letterly account, his voice). A few are general-purpose and useful
as-is or as a reference for writing your own:
`t3-fork`, `cmux-and-worktrees`, `co-ceo`, `thought-partner`, `communication-analysis`.

## Install

Install with the [`skills` CLI](https://skills.sh) (`npx skills`), the open
agent-skills package manager. Some skills also need `bun` or `uv` at
runtime — each skill's `SKILL.md` says so.

```bash
npx skills add rami-maalouf/skills --list          # see everything available
npx skills add rami-maalouf/skills -s t3-fork      # install one skill, project-local
npx skills add rami-maalouf/skills -s t3-fork -g   # install it globally instead
npx skills add rami-maalouf/skills --all           # install everything
```

`-g`/`--global` installs into `~/.claude/skills/<name>` (available in every
project); without it, the skill goes into `./.claude/skills/<name>` for the
current project only. `-a <agent>` targets a specific agent (`-a claude-code`,
or `-a '*'` for all supported agents) if you're not using Claude Code.
Installed skills and their source are tracked in `skills-lock.json`, which
`npx skills update` reads to pull in changes from this repo.

## Example: installing `t3-fork`

[`t3-fork`](skills/t3-fork) forks a T3 Code (the desktop AI coding app by Theo)
conversation into a new thread with the full prior context, optionally
branching from an earlier turn.

```bash
$ npx skills add rami-maalouf/skills -s t3-fork -g

◇  Installed 1 skill ────────────╮
│  ✓ t3-fork (copied)            │
│    → ~/.claude/skills/t3-fork  │
╰────────────────────────────────╯
```

Once installed, it shows up as `/t3-fork` in Claude Code. Typing `/t3-fork`, or
just asking to "fork this conversation" or "branch this chat", runs it.

## Repo layout

```
skills/<name>/SKILL.md       required — frontmatter (name, description) + instructions
skills/<name>/scripts/       optional — the code the skill runs
skill-collections/           bundles of skills grouped for a specific workspace
claude-code/, codex/, gemini/  shared agent config for each CLI
AGENTS.md, global_instructions.md   cross-agent behavior rules
setup_symlinks.sh            Rami's personal machine bootstrap (hardcoded paths;
                              not meant for other machines — use the skills CLI above instead)
```

## Writing a new skill

Add a directory under `skills/` with a `SKILL.md`:

```markdown
---
name: my-skill
description: One line covering what it does and when an agent should use it.
---

Instructions for the agent, in plain language.
```

Keep the description specific about trigger phrases — it is the only thing an
agent sees before deciding whether to open the skill. Put any code the skill
needs under `scripts/`, and note its runtime requirements (`bun`, `uv`, a
running app, etc.) directly in `SKILL.md` so anyone reading the file catches
it up front.

Keep the frontmatter `description` to a single plain-text line without an
unescaped `:` — the `skills` CLI parses it as YAML and a bare colon inside the
text breaks that parse, silently dropping the skill from `--list`.
