#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy"]
# ///
"""manage the speaker voiceprint store for speech-diarizer.

after a diarize run writes <name>.voiceprints.json, name the speakers you recognize:

    uv run --script enroll.py /path/to/out/call SPEAKER_00=Rami SPEAKER_01=Keith
    uv run --script enroll.py /path/to/out/call.voiceprints.json SPEAKER_02=Aman

inspect or prune the store:

    uv run --script enroll.py --list
    uv run --script enroll.py --remove Keith

the source argument is either the run's base path (no extension) or the
<name>.voiceprints.json sidecar directly. enrolling the same person from
multiple recordings makes their voiceprint more robust.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from voiceprints import CACHE_DIR, enroll as vp_enroll, load_store, save_store, store_path


def find_sidecar(arg: str) -> Path:
    """accept a .voiceprints.json directly, a run base path, or just the run's stem
    (looked up in the cache dir where diarize.py stashes embeddings)."""
    p = Path(arg).expanduser()
    if p.suffix == ".json" and p.exists():
        return p
    candidates = [
        p.with_suffix(".voiceprints.json"),          # adjacent to a given base path
        p.parent / f"{p.stem}.voiceprints.json",
        CACHE_DIR / f"{p.stem}.voiceprints.json",     # cached by diarize.py (default)
        CACHE_DIR / f"{p.name}.voiceprints.json",     # arg was a bare stem
    ]
    for cand in candidates:
        if cand.exists():
            return cand
    sys.exit(
        f"no voiceprints found for: {arg}\n"
        f"looked in the cache ({CACHE_DIR}) and next to the path. "
        "pass the run stem (e.g. 'workflow-tutorial-plan') or the .voiceprints.json directly."
    )


def main() -> None:
    ap = argparse.ArgumentParser(description="manage speaker voiceprints for speech-diarizer")
    ap.add_argument("source", nargs="?", help="run base path or <name>.voiceprints.json")
    ap.add_argument("labels", nargs="*", help="SPEAKER_XX=Name assignments")
    ap.add_argument("--list", action="store_true", help="list enrolled speakers and exit")
    ap.add_argument("--remove", metavar="NAME", help="remove an enrolled speaker and exit")
    ap.add_argument("--store", default=None,
                    help="voiceprint store path (default: $SPEECH_DIARIZER_VOICEPRINTS or ~/.config/speech-diarizer/voiceprints.json)")
    args = ap.parse_args()

    store = load_store(args.store)
    where = store_path(args.store)

    if args.list:
        if not store["speakers"]:
            print(f"no speakers enrolled yet (store: {where})")
            return
        print(f"store: {where}")
        print(f"model: {store.get('model')}")
        for name, sp in store["speakers"].items():
            print(f"  {name}: {len(sp['embeddings'])} sample(s)")
            for s in sp.get("samples", []):
                print(f"      - {s}")
        return

    if args.remove:
        if args.remove in store["speakers"]:
            del store["speakers"][args.remove]
            save_store(store, args.store)
            print(f"removed {args.remove}")
        else:
            print(f"{args.remove} not in store")
        return

    if not args.source or not args.labels:
        ap.error("provide a run source and at least one SPEAKER_XX=Name (or use --list/--remove)")

    sidecar = find_sidecar(args.source)
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    model = data.get("diarization_model")
    embeddings = data.get("raw_embeddings", {})
    if not embeddings:
        sys.exit(f"no raw_embeddings in {sidecar.name}")

    added = []
    for label in args.labels:
        if "=" not in label:
            sys.exit(f"bad label '{label}', expected SPEAKER_XX=Name")
        spk, name = (s.strip() for s in label.split("=", 1))
        if spk not in embeddings:
            sys.exit(f"{spk} not in {sidecar.name}; available: {', '.join(embeddings)}")
        vp_enroll(name, embeddings[spk], store, model, source=f"{data.get('source', '?')}#{spk}")
        added.append(f"{spk} -> {name}")

    save_store(store, args.store)
    print(f"enrolled into {where}:")
    for a in added:
        print(f"  {a}")


if __name__ == "__main__":
    main()
