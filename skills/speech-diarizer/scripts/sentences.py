#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""print one timestamped line per sentence from a diarize.py --json result.

    uv run --script sentences.py /path/to/out/talk.json
    uv run --script sentences.py /path/to/out/talk.json --no-speakers

each line is "[mm:ss] SPEAKER: sentence". sentences split on . ? ! and on
speaker changes. useful when a transcript needs references to exact moments
(for example a stand-up set and the notes on it).
"""

import argparse
import json
from pathlib import Path


def mmss(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def sentences(result: dict) -> list[tuple[float, str, str]]:
    out: list[tuple[float, str, str]] = []
    words: list[str] = []
    start, speaker = 0.0, ""
    last_t = 0.0

    for seg in result["segments"]:
        for w in seg.get("words", []):
            # words whisperx could not align have no start; reuse the last known time
            t = w.get("start", last_t)
            last_t = t
            spk = w.get("speaker", seg.get("speaker", "UNKNOWN"))
            if words and spk != speaker:
                out.append((start, speaker, " ".join(words)))
                words = []
            if not words:
                start, speaker = t, spk
            text = w["word"].strip()
            words.append(text)
            if text.endswith((".", "?", "!")):
                out.append((start, speaker, " ".join(words)))
                words = []

    if words:
        out.append((start, speaker, " ".join(words)))
    return out


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("json_path", type=Path, help="the <name>.json written by diarize.py --json")
    p.add_argument("--no-speakers", action="store_true", help="omit the speaker label")
    args = p.parse_args()

    result = json.loads(args.json_path.read_text(encoding="utf-8"))
    for start, speaker, text in sentences(result):
        label = "" if args.no_speakers else f"{speaker}: "
        print(f"[{mmss(start)}] {label}{text}")


if __name__ == "__main__":
    main()
