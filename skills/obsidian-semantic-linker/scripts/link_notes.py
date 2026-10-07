#!/usr/bin/env python3
"""Links notes in a target directory by appending a ## Related Notes section.

Uses Smart Connections (.smart-env/multi/*.ajson) for embeddings instead of
the legacy Nexus SQLite database.
"""
import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from utils.smart_connections import (
    get_vault_root,
    load_note_embeddings,
    normalize,
    cosine_similarity,
)

SIMILARITY_THRESHOLD = 0.45
TOP_K = 5


def append_related_notes(filepath, links):
    """Append ## Related Notes section to a file if not already present."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        if "## Related Notes" in content:
            return False
        section = "\n\n## Related Notes\n" + "".join(f"- [[{name}]]\n" for name in links)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(section)
        return True
    except Exception as e:
        print(f"  Error writing to {filepath}: {e}")
        return False


def process_files(embeddings, vault_root, target_dir="unprocessed", target_paths=None):
    """Find and link notes in target_dir against the full embedding index."""
    print(f"Loaded {len(embeddings)} embeddings. Linking notes in '{target_dir}'...")

    # normalize all vectors once, skipping notes that were moved or deleted
    # after smart connections indexed them (their old paths stay in the index)
    normed = {
        path: normalize(vec)
        for path, vec in embeddings.items()
        if os.path.exists(os.path.join(vault_root, path))
    }
    target_set = set(target_paths or [])

    updates = 0
    for current_path, current_vec in normed.items():
        if target_set and current_path not in target_set:
            continue
        if not target_set and not current_path.startswith(target_dir):
            continue

        full_path = os.path.join(vault_root, current_path)
        if not os.path.exists(full_path):
            continue

        scores = [
            (cosine_similarity(current_vec, other_vec), other_path)
            for other_path, other_vec in normed.items()
            if other_path != current_path and cosine_similarity(current_vec, other_vec) >= SIMILARITY_THRESHOLD
        ]
        scores.sort(reverse=True)

        # wiki-links resolve by note name, so keep each name once
        names = []
        for _, p in scores:
            name = os.path.splitext(os.path.basename(p))[0]
            if name not in names:
                names.append(name)
            if len(names) == TOP_K:
                break

        if not names:
            continue

        print(f"  Linking: {current_path} -> {names}")
        if append_related_notes(full_path, names):
            updates += 1

    return updates


def main(vault_root, target_files=None):
    """
    vault_root:   path to the Obsidian vault
    target_files: list of vault-relative paths to link; links all of unprocessed/ if None
    """
    try:
        embeddings = load_note_embeddings(vault_root)
    except FileNotFoundError as e:
        print(f"Error: {e}")
        return

    count = process_files(embeddings, vault_root, target_paths=target_files)
    print(f"Finished. Updated {count} file(s).")


if __name__ == "__main__":
    v_root = sys.argv[1] if len(sys.argv) > 1 else get_vault_root()
    files_to_link = sys.argv[2:] if len(sys.argv) > 2 else None
    main(v_root, target_files=files_to_link)
