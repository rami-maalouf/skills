# skills

Rami's collection of Claude Code skills, plus the agent config (Claude Code, Codex,
Gemini) that ties them together. Each skill is a self-contained directory with a
`SKILL.md` that tells an agent when and how to use it, and an optional `scripts/`
folder with the code it runs.

Most of these skills are built around Rami's own tools and context (his Obsidian
vault, his Letterly account, his voice, his immigration situation). A few are
general-purpose and useful as-is or as a reference for writing your own:
`t3-fork`, `cmux-and-worktrees`, `co-ceo`, `thought-partner`, `communication-analysis`.

## Install

Requires `git` and `bash`. Some skills also need `bun` or `uv` — each skill's
`SKILL.md` says so.

**From a clone:**

```bash
git clone https://github.com/rami-maalouf/skills.git
cd skills
./install.sh --list                 # see everything available
./install.sh t3-fork                # install one skill
./install.sh t3-fork thought-partner # install several
./install.sh --all                  # install everything
```

**Without cloning:**

```bash
curl -fsSL https://raw.githubusercontent.com/rami-maalouf/skills/main/install.sh | bash -s -- t3-fork
```

This caches a clone under `~/.cache/rami-skills` and keeps it updated on
later runs. Override with `SKILLS_HOME=/some/dir`.

By default, `install.sh` symlinks each skill into `~/.claude/skills/<name>` —
Claude Code's global skills directory. Since it's a symlink, `git pull` in the
repo (or in the cache dir, if you used the one-liner) updates the skill in
place; no need to reinstall. Pass `--copy` for a self-contained copy instead,
or `--target DIR` to install somewhere else, e.g. a project's `.claude/skills`:

```bash
./install.sh --target ./.claude/skills t3-fork   # project-local, not global
./install.sh --copy t3-fork                      # a copy, not a symlink
```

## Example: installing `t3-fork`

[`t3-fork`](skills/t3-fork) forks a T3 Code (the desktop AI coding app by Theo)
conversation into a new thread with the full prior context, optionally
branching from an earlier turn.

```bash
$ ./install.sh t3-fork
installed t3-fork -> /Users/rami/.claude/skills/t3-fork
  note: T3 Code must be running. Requires `bun`.

done: 1 skill(s) installed into /Users/rami/.claude/skills
these are symlinks into /Users/rami/Documents/life-os/ai-agents-config/skills - a git pull there updates them in place.
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
install.sh                   the installer above
setup_symlinks.sh            Rami's personal machine bootstrap (hardcoded paths;
                              not meant for other machines — use install.sh instead)
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
running app, etc.) directly in `SKILL.md` so `install.sh`'s "note:" line and
anyone reading the file catch it up front.
