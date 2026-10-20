import argparse
import json
import os
import shutil
import subprocess
import sys

SKILLS_DIR = "/Users/rami/Documents/life-os/ai-agents-config/skills"

# keep our output in order with the sub-process output
sys.stdout.reconfigure(line_buffering=True)

sys.path.append(SKILLS_DIR)
from utils.smart_connections import get_vault_root, wait_for_sc_indexing

# the sub-scripts only need the standard library; the shared skills venv keeps one python for all skills
PYTHON_EXE = os.path.join(SKILLS_DIR, ".venv", "bin", "python")
PROCESS_SCRIPT = os.path.join(SKILLS_DIR, "letterly-process", "scripts", "process.py")
METADATA_SCRIPT = os.path.join(SKILLS_DIR, "generate-metadata", "scripts", "generate_metadata.py")
LINK_SCRIPT = os.path.join(SKILLS_DIR, "obsidian-semantic-linker", "scripts", "link_notes.py")


def subprocess_env():
    # ensure sub-processes can import from utils/ inside skills/
    env = os.environ.copy()
    env["PYTHONPATH"] = SKILLS_DIR + os.pathsep + env.get("PYTHONPATH", "")
    return env


def unprocessed_notes(vault_root):
    unprocessed_dir = os.path.join(vault_root, "unprocessed")
    os.makedirs(unprocessed_dir, exist_ok=True)
    return sorted(f"unprocessed/{f}" for f in os.listdir(unprocessed_dir) if f.endswith(".md"))


def validate_metadata(vault_root, vault_paths, report_errors=True):
    """return the set of absolute paths with valid generated metadata, printing the errors of the rest."""
    full_paths = [os.path.join(vault_root, path) for path in vault_paths]
    result = subprocess.run(
        [PYTHON_EXE, METADATA_SCRIPT, "validate", "--json"] + full_paths,
        cwd=vault_root, env=subprocess_env(), capture_output=True, text=True,
    )
    if result.stderr:
        print(result.stderr)

    valid = set()
    try:
        report = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as e:
        print(f"Metadata validation output could not be parsed: {e}")
        return valid
    for item in report.get("files", []):
        if item.get("valid"):
            valid.add(os.path.abspath(item["path"]))
        elif report_errors:
            print(f"Pending metadata: {os.path.basename(item.get('path', 'unknown'))}")
            for error in item.get("errors", []):
                print(f"  - {error}")
    return valid


def run_window(vault_root, lookback_days):
    cmd = [PYTHON_EXE, PROCESS_SCRIPT, "--vault", vault_root, "window"]
    if lookback_days is not None:
        cmd += ["--lookback-days", str(lookback_days)]
    return subprocess.run(cmd, cwd=vault_root, env=subprocess_env()).returncode


def run_import(vault_root, batch_dir, plan):
    cmd = [PYTHON_EXE, PROCESS_SCRIPT, "--vault", vault_root, "import", batch_dir]
    if plan:
        cmd.append("--plan")
    code = subprocess.run(cmd, cwd=vault_root, env=subprocess_env()).returncode
    if plan:
        return code

    notes = unprocessed_notes(vault_root)
    valid = validate_metadata(vault_root, notes, report_errors=False) if notes else set()
    pending = [path for path in notes if os.path.abspath(os.path.join(vault_root, path)) not in valid]
    print("\nRun generate-metadata on these files, then run finish:")
    for path in pending:
        print(f"- {path}")
    return code


def run_finish(vault_root):
    new_vault_paths = unprocessed_notes(vault_root)
    if not new_vault_paths:
        print("No notes in unprocessed/. Workflow complete.")
        return 0

    print("\n--- Validating Generated Metadata ---")
    valid_metadata_paths = validate_metadata(vault_root, new_vault_paths)
    valid_vault_paths = [
        path for path in new_vault_paths
        if os.path.abspath(os.path.join(vault_root, path)) in valid_metadata_paths
    ]
    if not valid_vault_paths:
        print("No files with valid generated metadata. Leaving markdown files in unprocessed/.")
        return 0

    # the linker only sees notes that smart connections has embedded, which needs obsidian running
    print("\n--- Waiting For Smart Connections ---")
    wait_for_sc_indexing(vault_root, valid_vault_paths)

    print("\n--- Running Semantic Linker ---")
    subprocess.run([PYTHON_EXE, LINK_SCRIPT, vault_root] + valid_vault_paths, cwd=vault_root, env=subprocess_env())

    print("\n--- Moving metadata-ready files to Transcriptions ---")
    dest_dir = os.path.join(vault_root, "My Outputs/Transcriptions")
    os.makedirs(dest_dir, exist_ok=True)

    moved_count = 0
    for path in valid_vault_paths:
        filename = os.path.basename(path)
        try:
            shutil.move(os.path.join(vault_root, path), os.path.join(dest_dir, filename))
            print(f"Moved metadata-ready note: {filename}")
            moved_count += 1
        except Exception as e:
            print(f"Error moving {filename}: {e}")

    print("\nWorkflow Summary:")
    print(f"- Moved to Transcriptions: {moved_count}")
    print(f"- Remaining in unprocessed (pending metadata): {len(new_vault_paths) - len(valid_vault_paths)}")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="run the Letterly transcription workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    window = sub.add_parser("window", help="print the created_after date for letterly list_notes")
    window.add_argument("--lookback-days", type=int)

    imp = sub.add_parser("import", help="write fetched magic rewrites into unprocessed/")
    imp.add_argument("batch_dir")
    imp.add_argument("--plan", action="store_true", help="only report which rewrites still need their text")

    sub.add_parser("finish", help="validate metadata, link, and deliver to Transcriptions")

    args = parser.parse_args()
    root = get_vault_root()
    if args.command == "window":
        sys.exit(run_window(root, args.lookback_days))
    if args.command == "import":
        sys.exit(run_import(root, os.path.abspath(args.batch_dir), args.plan))
    sys.exit(run_finish(root))
