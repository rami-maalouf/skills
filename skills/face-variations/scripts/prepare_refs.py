# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow", "opencv-python-headless>=4.8,<5"]
# ///
"""turn raw photos into reference photos: find the face, crop to head and shoulders, save a 4:5 jpg.

tight crops give the image model more pixels of the face, and keep hands and props out of the refs.

usage:
  uv run prepare_refs.py --out-dir design/faces/rami/refs/beard "raw/IMG_1.jpg=front-neutral" "raw/IMG_2.jpg=3q-left-smile"
  uv run prepare_refs.py --out-dir /tmp/check raw/*.jpg     # no names: keeps the file names
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageOps

LONG_EDGE = 1600
DETECT_EDGE = 1200


def largest_face(rgb: Image.Image) -> tuple[float, float, float, float] | None:
    # detect on a smaller copy for speed, then scale the box back up
    scale = DETECT_EDGE / max(rgb.size)
    small = rgb.resize((round(rgb.width * scale), round(rgb.height * scale))) if scale < 1 else rgb
    scale = min(scale, 1)
    gray = cv2.cvtColor(np.asarray(small), cv2.COLOR_RGB2GRAY)
    faces = []
    for name in ("haarcascade_frontalface_default.xml", "haarcascade_profileface.xml"):
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + name)
        found = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=6, minSize=(60, 60))
        faces += [tuple(f) for f in found]
        if faces:
            break
    if not faces:
        return None
    x, y, w, h = max(faces, key=lambda f: f[2] * f[3])
    return x / scale, y / scale, w / scale, h / scale


def crop_box(size: tuple[int, int], face: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    x, y, w, h = face
    width = min(w * 3.0, size[0])
    height = min(width * 5 / 4, size[1])
    width = height * 4 / 5
    cx = x + w / 2
    top = y - h * 0.85
    left = min(max(cx - width / 2, 0), size[0] - width)
    top = min(max(top, 0), size[1] - height)
    return round(left), round(top), round(left + width), round(top + height)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", nargs="+", help="SRC or SRC=NAME (NAME without extension)")
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out = Path(args.out_dir).expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    failed = 0
    for item in args.photos:
        src, _, name = item.partition("=")
        src_path = Path(src).expanduser()
        if not src_path.is_file():
            print(f"FAIL {src}: not found", file=sys.stderr)
            failed += 1
            continue
        im = ImageOps.exif_transpose(Image.open(src_path)).convert("RGB")
        face = largest_face(im)
        if face is None:
            print(f"FAIL {src_path.name}: no face found. crop it by hand.", file=sys.stderr)
            failed += 1
            continue
        crop = im.crop(crop_box(im.size, face))
        crop.thumbnail((LONG_EDGE, LONG_EDGE), Image.LANCZOS)
        dest = out / f"{name or src_path.stem}.jpg"
        crop.save(dest, quality=92)
        print(f"ok   {dest.name} ({crop.width}x{crop.height}, face {round(face[2])} px wide in the source)")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
