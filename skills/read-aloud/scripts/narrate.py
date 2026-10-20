#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["kokoro>=0.9.4", "misaki[en]>=0.9.4", "soundfile>=0.12"]
# ///
"""
narrate.py - read a narration script aloud with the local kokoro neural voice.

Usage:
    uv run narrate.py narration.txt -o "~/Downloads/Title.mp3" --title "Title" --artist "Author"
    uv run narrate.py narration.txt -o sample.mp3 --limit 4          # quick sample
    uv run narrate.py narration.txt -o out.mp3 --voice bm_george --speed 1.0

script format: paragraphs separated by blank lines. a paragraph under 110 characters
counts as a heading and gets a longer pause. a line that is exactly [pause N]
inserts N seconds of silence (use it between chapters).
output: loudness-normalized mp3 (needs ffmpeg on PATH).
"""

import argparse
import os
import re
import subprocess
import sys
import tempfile

import numpy as np
import soundfile as sf

SR = 24000


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--speed", type=float, default=0.95)
    ap.add_argument("--limit", type=int, help="only the first n paragraphs")
    ap.add_argument("--title")
    ap.add_argument("--artist")
    a = ap.parse_args()

    from kokoro import KPipeline

    # the first letter of a kokoro voice is its language: a = american, b = british
    pipe = KPipeline(lang_code=a.voice[0], repo_id="hexgrad/Kokoro-82M")
    paras = [p.strip() for p in open(a.src).read().split("\n\n") if p.strip()][: a.limit]

    def silence(s: float) -> np.ndarray:
        return np.zeros(int(SR * s), dtype=np.float32)

    chunks = []
    for i, p in enumerate(paras, 1):
        m = re.fullmatch(r"\[pause ([\d.]+)\]", p)
        if m:
            chunks.append(silence(float(m.group(1))))
            continue
        for _, _, audio in pipe(p, voice=a.voice, speed=a.speed, split_pattern=r"\n+"):
            chunks.append(audio.numpy() if hasattr(audio, "numpy") else np.asarray(audio))
        chunks.append(silence(1.1 if len(p) < 110 else 0.7))
        print(f"{i}/{len(paras)}", flush=True)

    out = os.path.expanduser(a.out)
    with tempfile.TemporaryDirectory() as tmp:
        wav = os.path.join(tmp, "full.wav")
        sf.write(wav, np.concatenate(chunks), SR)
        cmd = ["ffmpeg", "-y", "-loglevel", "error", "-i", wav,
               "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "libmp3lame", "-b:a", "128k"]
        if a.title:
            cmd += ["-metadata", f"title={a.title}"]
        if a.artist:
            cmd += ["-metadata", f"artist={a.artist}"]
        subprocess.run(cmd + [out], check=True)
    print(f"done -> {out}", file=sys.stderr)


if __name__ == "__main__":
    main()
