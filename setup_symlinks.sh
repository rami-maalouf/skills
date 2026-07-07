#!/bin/bash

# Define paths
CONFIG_DIR="/Users/rami/Documents/life-os/ai-agents-config"

echo "Setting up symlinks for all AI agents..."

# Function to safely create symlinks
safe_link() {
    local source_file="$1"
    local target_link="$2"

    # Check if target exists and is NOT a symlink
    if [ -e "$target_link" ] && [ ! -L "$target_link" ]; then
        echo "  [Backup] Existing file found. Backing up to ${target_link}.bak"
        mv "$target_link" "${target_link}.bak"
    fi

    ln -sf "$source_file" "$target_link"
    echo "  [Linked] $target_link -> $source_file"
}

# --- Shared agent instructions (single origin: AGENTS.md) ---
echo "Linking shared AGENTS.md..."
mkdir -p ~/.claude ~/.codex ~/.gemini
safe_link "$CONFIG_DIR/AGENTS.md" ~/AGENTS.md
safe_link "$CONFIG_DIR/AGENTS.md" ~/.claude/CLAUDE.md
safe_link "$CONFIG_DIR/AGENTS.md" ~/.codex/AGENTS.md
safe_link "$CONFIG_DIR/AGENTS.md" ~/.gemini/GEMINI.md

# --- Claude Code ---
echo "Linking Claude Code..."
mkdir -p ~/.claude
safe_link "$CONFIG_DIR/claude-code/config/settings.json" ~/.claude/settings.json

# --- Codex ---
echo "Linking Codex..."
mkdir -p ~/.codex/rules
safe_link "$CONFIG_DIR/codex/config.toml" ~/.codex/config.toml
safe_link "$CONFIG_DIR/codex/rules/default.rules" ~/.codex/rules/default.rules

# --- Gemini ---
echo "Linking Gemini..."
mkdir -p ~/.gemini
# GEMINI.md is linked to the shared AGENTS.md above
# safe_link "$CONFIG_DIR/gemini/settings.json" ~/.gemini/settings.json

# --- Antigravity ---
echo "Linking Antigravity..."
mkdir -p ~/.gemini/antigravity
# safe_link "$CONFIG_DIR/gemini/commandAllowlist.txt" ~/.gemini/antigravity/commandAllowlist.txt

echo "All symlinks have been safely created!"
