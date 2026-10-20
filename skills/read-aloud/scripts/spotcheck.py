#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["mlx-whisper>=0.4"]
# ///
"""
spotcheck.py - transcribe short slices of the finished audio to confirm the voice
says the right words. apple silicon only (mlx).

Usage:
    uv run spotcheck.py out.mp3                 # start, middle and end, 40s each
    uv run spotcheck.py out.mp3 --at 0 600 1800 --seconds 30
"""

import argparse
import os
import subprocess
import tempfile

import mlx_whisper


def duration(path: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True, check=True)
    return float(r.stdout.strip())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("--at", type=float, nargs="*")
    ap.add_argument("--seconds", type=float, default=40)
    a = ap.parse_args()

    total = duration(a.audio)
    points = a.at if a.at else [0, total / 2, max(total - a.seconds, 0)]
    print(f"duration {total / 60:.1f} min")
    with tempfile.TemporaryDirectory() as tmp:
        for t in points:
            clip = os.path.join(tmp, f"{int(t)}.wav")
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-t", str(a.seconds),
                            "-i", a.audio, "-ac", "1", "-ar", "16000", clip], check=True)
            r = mlx_whisper.transcribe(clip, path_or_hf_repo="mlx-community/whisper-small.en-mlx")
            print(f"\n[{int(t // 60)}:{int(t % 60):02d}] {r['text'].strip()}")


if __name__ == "__main__":
    main()
