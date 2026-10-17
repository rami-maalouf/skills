#!/bin/bash

# define paths
CONFIG_DIR="/Users/rami/Documents/life-os/ai-agents-config"
WORKSPACE_DIR="/Users/rami/Documents/life-os"
MODE="${1:-all}"

case "$MODE" in
    all) echo "Setting up symlinks for all AI agents..." ;;
    --collections-only) echo "Setting up project skill collections..." ;;
    *)
        echo "Usage: bash setup_symlinks.sh [--collections-only]"
        exit 2
        ;;
esac

# safely create a symlink without overwriting a real file
safe_link() {
    local source_file="$1"
    local target_link="$2"
    local backup_path

    # preserve real files and directories before linking
    if [ -e "$target_link" ] && [ ! -L "$target_link" ]; then
        backup_path="${target_link}.bak"
        if [ -e "$backup_path" ] || [ -L "$backup_path" ]; then
            backup_path="${target_link}.bak.$(date +%Y%m%d-%H%M%S)"
        fi
        echo "  [Backup] Existing file found. Backing up to $backup_path"
        mv "$target_link" "$backup_path"
    fi

    ln -sfn "$source_file" "$target_link"
    echo "  [Linked] $target_link -> $source_file"
}

# install one canonical skill into every project-level agent skill surface
link_collection_skill() {
    local skill_name="$1"
    local target_dir="$2"
    local source_dir="$CONFIG_DIR/skills/$skill_name"

    if [ ! -f "$source_dir/SKILL.md" ]; then
        echo "  [Error] Missing canonical skill: $source_dir/SKILL.md"
        return 1
    fi

    safe_link "$source_dir" "$target_dir/.agents/skills/$skill_name"
    safe_link "../../.agents/skills/$skill_name" "$target_dir/.agent/skills/$skill_name"
    safe_link "../../.agents/skills/$skill_name" "$target_dir/.claude/skills/$skill_name"
}

# materialize each tracked skill collection as a workspace directory
link_skill_collections() {
    local collection_dir
    local collection_name
    local collection_path
    local target_dir
    local skill_name

    for collection_dir in "$CONFIG_DIR/skill-collections"/*; do
        [ -d "$collection_dir" ] || continue

        collection_name="$(basename "$collection_dir")"
        target_dir="$WORKSPACE_DIR/$collection_name"

        # an optional "path" file places the workspace below the root (e.g. creative-arts/storytelling)
        if [ -f "$collection_dir/path" ]; then
            read -r collection_path < "$collection_dir/path"
            target_dir="$WORKSPACE_DIR/$collection_path"
        fi

        echo "Linking skill collection: $collection_name..."
        mkdir -p "$target_dir/.agents/skills"
        mkdir -p "$target_dir/.agent/skills"
        mkdir -p "$target_dir/.claude/skills"

        if [ -f "$collection_dir/README.md" ]; then
            safe_link "$collection_dir/README.md" "$target_dir/README.md"
        fi

        if [ ! -f "$collection_dir/skills.txt" ]; then
            echo "  [Error] Missing collection manifest: $collection_dir/skills.txt"
            return 1
        fi

        while IFS= read -r skill_name || [ -n "$skill_name" ]; do
            case "$skill_name" in
                ""|\#*) continue ;;
            esac
            link_collection_skill "$skill_name" "$target_dir" || return 1
        done < "$collection_dir/skills.txt"
    done
}

if [ "$MODE" = "--collections-only" ]; then
    link_skill_collections
    echo "All project skill collections have been linked!"
    exit 0
fi

# shared agent instructions from one source
echo "Linking shared AGENTS.md..."
mkdir -p ~/.claude ~/.codex ~/.gemini
safe_link "$CONFIG_DIR/AGENTS.md" ~/AGENTS.md
safe_link "$CONFIG_DIR/AGENTS.md" ~/.claude/CLAUDE.md
safe_link "$CONFIG_DIR/AGENTS.md" ~/.codex/AGENTS.md
safe_link "$CONFIG_DIR/AGENTS.md" ~/.gemini/GEMINI.md

# claude code
echo "Linking Claude Code..."
mkdir -p ~/.claude
safe_link "$CONFIG_DIR/claude-code/config/settings.json" ~/.claude/settings.json

# codex
echo "Linking Codex..."
mkdir -p ~/.codex/rules
safe_link "$CONFIG_DIR/codex/config.toml" ~/.codex/config.toml
safe_link "$CONFIG_DIR/codex/rules/default.rules" ~/.codex/rules/default.rules

# gemini
echo "Linking Gemini..."
mkdir -p ~/.gemini
# gemini.md is linked to the shared agents.md above
# safe_link "$CONFIG_DIR/gemini/settings.json" ~/.gemini/settings.json

# antigravity
echo "Linking Antigravity..."
mkdir -p ~/.gemini/antigravity
# safe_link "$CONFIG_DIR/gemini/commandAllowlist.txt" ~/.gemini/antigravity/commandAllowlist.txt

# global skills: canonical copy in ai-agents-config, exposed to every agent
# via ~/.agents/skills, with ~/.claude/skills pointing at that
echo "Linking global skills..."
mkdir -p ~/.agents/skills ~/.claude/skills
for skill_name in t3-fork co-ceo metacognitive-architect thought-partner; do
    safe_link "$CONFIG_DIR/skills/$skill_name" ~/.agents/skills/"$skill_name"
    safe_link "../../.agents/skills/$skill_name" ~/.claude/skills/"$skill_name"
done

link_skill_collections

echo "All symlinks have been safely created!"
