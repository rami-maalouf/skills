"""
shared utilities for reading Smart Connections embeddings from .smart-env/multi/*.ajson files.

Smart Connections stores per-note NDJSON files where each line is:
  "smart_sources:path": {..., "embeddings": {"model": {"vec": [...]}}}
  "smart_blocks:path#heading": {..., "embeddings": {"model": {"vec": [...]}}, "lines": [start, end]}
"""
import os
import json
import math
import time

SMART_ENV_DIR = ".smart-env/multi"
DEFAULT_MODEL = "TaylorAI/bge-micro-v2"


def get_vault_root():
    """Detect vault root by looking for .smart-env directory."""
    candidates = [
        os.getcwd(),
        "/Users/rami/Documents/life-os/Obsidian",
        "/Users/rami/Library/Mobile Documents/iCloud~md~obsidian/Documents/Obsidian",
    ]
    for c in candidates:
        if os.path.exists(os.path.join(c, ".smart-env")):
            return c
    return os.getcwd()


def path_to_ajson_name(note_path):
    """Convert a vault-relative note path to its Smart Connections .ajson filename.

    Example: 'My Notes/Foo bar.md' -> 'My_Notes_Foo_bar_md.ajson'
    """
    return note_path.replace("/", "_").replace(" ", "_").replace(".", "_") + ".ajson"


def _parse_ajson_file(filepath):
    """Parse a Smart Connections .ajson file into a dict of {key: entry}.

    Each line is NDJSON of the form: "key": {...}, or "key": null,
    """
    entries = {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip().rstrip(",")
                if not line:
                    continue
                try:
                    obj = json.loads("{" + line + "}")
                    entries.update(obj)
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return entries


SF_DATALESS = 0x40000000  # macos flag: file content lives only in icloud


def _is_dataless(filepath):
    """True when icloud has evicted the file and only a placeholder is on disk."""
    try:
        return bool(getattr(os.stat(filepath), "st_flags", 0) & SF_DATALESS)
    except OSError:
        return False


EMBED_DIM = 384  # TaylorAI/bge-micro-v2


def _load_matrix_file_embeddings(vault_root):
    """Load note-level embeddings from the newer Smart Connections layout.

    Newer plugin versions write one ndjson index at
    .smart-env/smart_sources/smart_sources.ajson and store the vectors as a
    flat float32 matrix in a sibling file. Each source entry points at its
    row via embedding.default.<file>.file_i.

    Returns: dict of {vault_relative_path: vector_list}
    """
    import struct

    sources_dir = os.path.join(vault_root, ".smart-env", "smart_sources")
    index_path = os.path.join(sources_dir, "smart_sources.ajson")
    if not os.path.exists(index_path):
        return {}

    matrices = {}

    def matrix(name):
        if name not in matrices:
            path = os.path.join(sources_dir, name)
            if not os.path.exists(path):
                matrices[name] = None
            else:
                with open(path, "rb") as f:
                    matrices[name] = f.read()
        return matrices[name]

    embeddings = {}
    row_bytes = EMBED_DIM * 4
    for key, val in _parse_ajson_file(index_path).items():
        if not key.startswith("smart_sources:") or not isinstance(val, dict):
            continue
        slots = (val.get("embedding") or {}).get("default") or {}
        for slot in slots.values():
            if not isinstance(slot, dict) or "file_i" not in slot:
                continue
            data = matrix(slot.get("file"))
            if data is None:
                continue
            start = slot["file_i"] * row_bytes
            if start + row_bytes > len(data):
                continue
            vec = list(struct.unpack_from(f"<{EMBED_DIM}f", data, start))
            note_path = val.get("path") or key[len("smart_sources:"):]
            embeddings[note_path] = vec
            break
    return embeddings


def load_note_embeddings(vault_root, model=DEFAULT_MODEL):
    """Load note-level embeddings from all .ajson files.

    Reads the legacy per-note files in .smart-env/multi/ and the newer
    smart_sources matrix layout. Newer data wins when both exist.

    Returns: dict of {vault_relative_path: vector_list}
    Skips notes with null entries (not yet embedded by SC).
    """
    smart_env = os.path.join(vault_root, SMART_ENV_DIR)
    if not os.path.exists(smart_env):
        raise FileNotFoundError(f"Smart Connections data not found at {smart_env}")

    embeddings = {}
    for filename in os.listdir(smart_env):
        if not filename.endswith(".ajson"):
            continue
        filepath = os.path.join(smart_env, filename)
        # the legacy files stopped updating on 2026-10-02, so icloud evicts
        # them. reading an evicted file blocks on a download, one file at a
        # time, which stalls the linker for many minutes. skip them.
        if _is_dataless(filepath):
            continue
        entries = _parse_ajson_file(filepath)
        for key, val in entries.items():
            if not key.startswith("smart_sources:"):
                continue
            if not val:
                continue
            vec = val.get("embeddings", {}).get(model, {}).get("vec")
            if vec:
                note_path = val.get("path") or key[len("smart_sources:"):]
                embeddings[note_path] = vec

    embeddings.update(_load_matrix_file_embeddings(vault_root))
    return embeddings


def load_block_embeddings(vault_root, model=DEFAULT_MODEL):
    """Load block-level (per-heading) embeddings from all .ajson files.

    Returns: dict of {block_key: {"path": str, "vec": list, "lines": [start, end]}}
    Block key format: 'note/path.md#Heading#Subheading'
    """
    smart_env = os.path.join(vault_root, SMART_ENV_DIR)
    if not os.path.exists(smart_env):
        raise FileNotFoundError(f"Smart Connections data not found at {smart_env}")

    blocks = {}
    for filename in os.listdir(smart_env):
        if not filename.endswith(".ajson"):
            continue
        filepath = os.path.join(smart_env, filename)
        if _is_dataless(filepath):
            continue
        entries = _parse_ajson_file(filepath)
        for key, val in entries.items():
            if not key.startswith("smart_blocks:"):
                continue
            if not val:
                continue
            vec = val.get("embeddings", {}).get(model, {}).get("vec")
            if not vec:
                continue
            block_key = val.get("key") or key[len("smart_blocks:"):]
            note_path = block_key.split("#")[0] if "#" in block_key else block_key
            blocks[block_key] = {
                "path": note_path,
                "vec": vec,
                "lines": val.get("lines"),
            }

    return blocks


def normalize(v):
    norm = math.sqrt(sum(x * x for x in v))
    if norm == 0:
        return v
    return [x / norm for x in v]


def cosine_similarity(v1, v2):
    """Dot product of two vectors. Assumes both are already normalized."""
    return sum(a * b for a, b in zip(v1, v2))


def wait_for_sc_indexing(vault_root, note_paths, timeout=90):
    """Poll .smart-env/multi/ until all note_paths have .ajson files with embeddings.

    note_paths: list of vault-relative paths (e.g. ['unprocessed/Foo.md'])
    Returns True if all indexed within timeout, False otherwise.
    """
    smart_env = os.path.join(vault_root, SMART_ENV_DIR)
    start = time.time()

    print(f"Waiting for Smart Connections to index {len(note_paths)} file(s)...")
    while time.time() - start < timeout:
        indexed = load_note_embeddings(vault_root)
        missing = [p for p in note_paths if p not in indexed]
        if not missing:
            print("All files indexed by Smart Connections.")
            return True
        remaining = int(timeout - (time.time() - start))
        print(f"  {len(missing)} file(s) still pending... ({remaining}s left)")
        time.sleep(6)

    print(f"Warning: indexing timed out. Proceeding with available embeddings.")
    return False
