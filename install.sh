#!/usr/bin/env bash
# install one, several, or all skills from this repo into a claude code
# skills directory (default: ~/.claude/skills).
#
# works two ways:
#   - run from inside a clone of this repo: links straight from ./skills
#   - run standalone (e.g. piped from curl): clones/updates a cache at
#     ~/.cache/rami-skills and links from there
#
# usage:
#   ./install.sh --list                    list every available skill
#   ./install.sh t3-fork                   install one skill
#   ./install.sh t3-fork rami-voice        install several
#   ./install.sh --all                     install everything
#   ./install.sh --target DIR t3-fork      install into a custom directory
#   ./install.sh --copy t3-fork            copy instead of symlink
#
# one-liner (no clone needed):
#   curl -fsSL https://raw.githubusercontent.com/rami-maalouf/skills/main/install.sh | bash -s -- t3-fork

set -euo pipefail

REPO_URL="${SKILLS_REPO_URL:-https://github.com/rami-maalouf/skills.git}"
BRANCH="${SKILLS_REPO_BRANCH:-main}"
CACHE_DIR="${SKILLS_HOME:-$HOME/.cache/rami-skills}"

usage() {
  cat <<'EOF'
install skills from this repo

usage:
  install.sh --list
  install.sh [--target DIR] [--copy] <skill> [<skill> ...]
  install.sh [--target DIR] [--copy] --all

options:
  --list          print every available skill with its description, then exit
  --all           install every skill in the repo
  --target DIR    where to install (default: ~/.claude/skills)
  --copy          copy the skill directory instead of symlinking it
  --symlink       symlink it (default)
  -h, --help      show this help

env:
  SKILLS_REPO_URL     override the repo to install from
  SKILLS_REPO_BRANCH  override the branch (default: main)
  SKILLS_HOME         where to cache a standalone clone (default: ~/.cache/rami-skills)
EOF
}

# find the skills/ directory to install from: the clone this script lives in,
# or a cached clone we manage ourselves if run standalone.
resolve_repo_dir() {
  local script_dir=""
  if [ -n "${BASH_SOURCE[0]:-}" ]; then
    script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd -P)" || script_dir=""
  fi
  if [ -n "$script_dir" ] && [ -d "$script_dir/skills" ]; then
    echo "$script_dir"
    return
  fi

  if [ -d "$CACHE_DIR/.git" ]; then
    git -C "$CACHE_DIR" pull --quiet --ff-only origin "$BRANCH" 1>&2
  else
    mkdir -p "$(dirname -- "$CACHE_DIR")"
    git clone --quiet --branch "$BRANCH" "$REPO_URL" "$CACHE_DIR" 1>&2
  fi
  echo "$CACHE_DIR"
}

available_skills() {
  local skills_dir="$1"
  for dir in "$skills_dir"/*/; do
    local name
    name="$(basename -- "$dir")"
    [ -f "$dir/SKILL.md" ] && echo "$name"
  done | sort
}

# best-effort read of the frontmatter `description:` line, including the
# `>-` yaml block-scalar style a couple of skills use.
skill_description() {
  awk '
    /^description:/ {
      sub(/^description: */, "")
      if ($0 == ">-" || $0 == "|" || $0 == "") { getline; sub(/^[[:space:]]+/, "") }
      gsub(/^"|"$/, "")
      print
      exit
    }
  ' "$1"
}

truncate_text() {
  local text="$1" max="${2:-96}"
  if [ "${#text}" -gt "$max" ]; then
    echo "${text:0:$max}..."
  else
    echo "$text"
  fi
}

TARGET="$HOME/.claude/skills"
MODE="symlink"
LIST=false
ALL=false
NAMES=()

while [ $# -gt 0 ]; do
  case "$1" in
    --list) LIST=true; shift ;;
    --all) ALL=true; shift ;;
    --target) TARGET="${2:?--target needs a directory}"; shift 2 ;;
    --copy) MODE="copy"; shift ;;
    --symlink) MODE="symlink"; shift ;;
    -h|--help) usage; exit 0 ;;
    --) shift; NAMES+=("$@"); break ;;
    -*) echo "error: unknown flag $1" >&2; usage >&2; exit 1 ;;
    *) NAMES+=("$1"); shift ;;
  esac
done

REPO_DIR="$(resolve_repo_dir)"
SKILLS_DIR="$REPO_DIR/skills"

if $LIST; then
  while IFS= read -r name; do
    desc="$(skill_description "$SKILLS_DIR/$name/SKILL.md")"
    printf '%-28s %s\n' "$name" "$(truncate_text "$desc")"
  done < <(available_skills "$SKILLS_DIR")
  exit 0
fi

if $ALL; then
  while IFS= read -r name; do NAMES+=("$name"); done < <(available_skills "$SKILLS_DIR")
elif [ "${#NAMES[@]}" -eq 0 ]; then
  echo "error: pass one or more skill names, or --all. Run with --list to see what's available." >&2
  exit 1
fi

unknown=()
for name in "${NAMES[@]}"; do
  [ -f "$SKILLS_DIR/$name/SKILL.md" ] || unknown+=("$name")
done
if [ "${#unknown[@]}" -gt 0 ]; then
  echo "error: unknown skill(s): ${unknown[*]}" >&2
  echo "run with --list to see available skills" >&2
  exit 1
fi

mkdir -p "$TARGET"
for name in "${NAMES[@]}"; do
  src="$SKILLS_DIR/$name"
  dst="$TARGET/$name"
  if [ "$MODE" = "symlink" ]; then
    ln -sfn "$src" "$dst"
  else
    rm -rf "$dst"
    cp -R "$src" "$dst"
  fi
  echo "installed $name -> $dst"
  note="$(grep -m1 -i 'requires' "$src/SKILL.md" 2>/dev/null || true)"
  [ -n "$note" ] && printf '  note: %s\n' "$note"
done

echo
echo "done: ${#NAMES[@]} skill(s) installed into $TARGET"
if [ "$MODE" = "symlink" ]; then
  echo "these are symlinks into $SKILLS_DIR - a git pull there updates them in place."
fi
