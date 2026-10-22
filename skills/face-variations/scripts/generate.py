# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""make new images of one real person from their reference photos, with codex's built-in image tool.

the built-in tool runs on the chatgpt plan that codex is signed in with, so no api key is needed.
each variant is its own `codex exec` run, so one bad result never affects the others.

usage:
  uv run generate.py --face design/faces/rami --look beard --prompt "laughing, head tilted left"
  uv run generate.py --face design/faces/rami --prompt "shocked" --prompt "skeptical" --count 2 --out design/thumbnails/x/faces
  uv run generate.py --face design/faces/rami --prompt "shocked" --dry-run
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from catalog import tag as catalog_tag

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_REFS = 8
TIMEOUT_S = 600

FRAMING = {
    "landscape": "landscape 16:9, head and shoulders",
    "portrait": "portrait 2:3, head and shoulders",
    "square": "square 1:1, head and shoulders",
}

PROMPT = """Use $imagegen with the built-in image_gen tool. Do not use the CLI fallback. Make exactly one image.

Use case: identity-preserve
Asset type: {asset}
Input images: {images} of one real person{name}. Take only the identity from them: face, hair, facial hair and skin. Ignore their backgrounds, text, logos and lighting.
Identity lock: keep the same bone structure, face shape, eye shape and color, eyebrows, nose, lips, ears, hairline, hair texture and volume, facial hair shape and density, glasses or no glasses, skin tone and age as the references. Do not beautify, slim, smooth, average or restyle the face.
{profile}Primary request: {prompt}
Composition/framing: {framing}
Scene/backdrop: {backdrop}
Constraints: no text, no logos, no watermark, no extra people.

When done, reply with one line: IMAGE_PATH: <absolute path of the generated file>
"""


def codex_home() -> Path:
    return Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))


def slug(text: str, n: int = 40) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:n].strip("-") or "variant"


def images_in(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*") if p.suffix.lower() in IMAGE_EXTS)


def pick_look(face: Path, look: str | None) -> str | None:
    # a look is one folder under refs/: the hair, facial hair and glasses of one period. never mix looks in one run
    refs = face / "refs"
    looks = sorted(p.name for p in refs.iterdir() if p.is_dir()) if refs.is_dir() else []
    if look:
        if look not in looks:
            sys.exit(f"no look '{look}' in {refs}. looks: {', '.join(looks) or 'none'}")
        return look
    if images_in(refs) or not looks:
        return None
    if len(looks) == 1:
        return looks[0]
    profile = face / "profile.md"
    match = re.search(r"^default look:\s*(\S+)", profile.read_text(), re.MULTILINE) if profile.is_file() else None
    if match and match.group(1) in looks:
        return match.group(1)
    sys.exit(f"{face.name} has several looks: {', '.join(looks)}. pick one with --look.")


def list_refs(face: Path, look: str | None, picked: list[str]) -> list[Path]:
    folder = face / "refs" / look if look else face / "refs"
    if picked:
        refs = [Path(p).expanduser().resolve() for p in picked]
    else:
        refs = images_in(folder)
        if len(refs) > MAX_REFS:
            print(f"note: {len(refs)} refs found, using the first {MAX_REFS}. pick refs with --ref to choose.", file=sys.stderr)
            refs = refs[:MAX_REFS]
    missing = [str(p) for p in refs if not p.is_file()]
    if missing:
        sys.exit(f"missing reference photos: {', '.join(missing)}")
    if not refs:
        sys.exit(f"no reference photos in {folder}. add 8-12 photos first (see SKILL.md).")
    return refs


def identity_lines(face: Path, look: str | None) -> str:
    # bullets under "## identity lock" (every look) and "## look: <name>" in profile.md name the features that drift
    profile = face / "profile.md"
    if not profile.is_file():
        return ""
    wanted = {"## identity lock"} | ({f"## look: {look}"} if look else set())
    lines, inside = [], False
    for line in profile.read_text().splitlines():
        if line.startswith("## "):
            inside = line.strip().lower() in wanted
            continue
        if inside and line.strip().startswith("- "):
            lines.append(line.strip()[2:])
    return "".join(f"Identity detail: {line}\n" for line in lines)


def person_name(face: Path) -> str:
    profile = face / "profile.md"
    if profile.is_file():
        first = profile.read_text().splitlines()[0:1]
        if first and first[0].startswith("# "):
            return f" ({first[0][2:].strip()})"
    return f" ({face.name})"


def run_one(job: dict, refs: list[Path], workdir: Path) -> dict:
    started = time.time()
    run_dir = Path(tempfile.mkdtemp(prefix="face-variation-", dir=workdir))
    last = run_dir / "last.txt"
    cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "--json", "-o", str(last), "-C", str(run_dir)]
    for ref in refs:
        cmd.append(f"--image={ref}")
    # the prompt goes in on stdin: -i takes several files, so a positional prompt after it is read as a file
    try:
        proc = subprocess.run(cmd, check=False, input=job["prompt"], capture_output=True, text=True, timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {**job, "ok": False, "error": f"timed out after {TIMEOUT_S}s", "seconds": round(time.time() - started)}

    thread_id = None
    for line in proc.stdout.splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "thread.started":
            thread_id = event.get("thread_id")
            break

    # codex saves built-in images under generated_images/<thread id>/; the IMAGE_PATH line is the backup
    found = []
    if thread_id:
        found = sorted((codex_home() / "generated_images" / thread_id).glob("*.png"), key=lambda p: p.stat().st_mtime)
    if not found and last.is_file():
        match = re.search(r"IMAGE_PATH:\s*(\S+)", last.read_text())
        if match and Path(match.group(1)).is_file():
            found = [Path(match.group(1))]

    result = {**job, "thread_id": thread_id, "seconds": round(time.time() - started)}
    if proc.returncode != 0 or not found:
        tail = (proc.stderr or "").strip().splitlines()[-5:]
        return {**result, "ok": False, "error": f"codex exit {proc.returncode}, no image found", "stderr": tail}

    shutil.copy2(found[-1], job["out_file"])
    shutil.rmtree(run_dir, ignore_errors=True)
    return {**result, "ok": True, "source": str(found[-1])}


def checker(size: tuple[int, int], step: int = 16) -> Image.Image:
    bg = Image.new("RGB", size, "#3a3d44")
    draw = ImageDraw.Draw(bg)
    for y in range(0, size[1], step):
        for x in range((y // step) % 2 * step, size[0], step * 2):
            draw.rectangle([x, y, x + step - 1, y + step - 1], fill="#4a4e56")
    return bg


def load_tile(file: Path, box: tuple[int, int]) -> Image.Image:
    im = ImageOps.contain(ImageOps.exif_transpose(Image.open(file)), box)
    if im.mode in ("RGBA", "LA", "P"):
        # a checkerboard shows where the image is transparent, so cut edges are easy to judge
        im = im.convert("RGBA")
        bg = checker(im.size)
        bg.paste(im, mask=im.getchannel("A"))
        return bg
    return im.convert("RGB")


def contact_sheet(refs: list[Path], results: list[dict], path: Path) -> None:
    box, gap, label_h, per_row = (480, 320), 16, 30, 4
    font = ImageFont.load_default(size=18)
    sections = [("references", refs), ("variants", [Path(r["out_file"]) for r in results if r["ok"]])]
    rows = []
    for title, files in sections:
        tiles = []
        for f in files:
            try:
                tiles.append((f.name, load_tile(f, box)))
            except OSError as err:
                print(f"note: left {f.name} out of the contact sheet: {err}", file=sys.stderr)
        for i in range(0, max(len(tiles), 1), per_row):
            rows.append((title if i == 0 else None, tiles[i : i + per_row]))

    cols = max(len(tiles) for _, tiles in rows) or 1
    row_heights = [max((im.height for _, im in tiles), default=0) for _, tiles in rows]
    height = gap + sum((label_h if title else 0) + h + label_h + gap for (title, _), h in zip(rows, row_heights))
    sheet = Image.new("RGB", (gap + cols * (box[0] + gap), height), "#16181d")
    draw = ImageDraw.Draw(sheet)
    y = gap
    for (title, tiles), row_h in zip(rows, row_heights):
        if title:
            draw.text((gap, y + 4), title, fill="#9aa3ad", font=font)
            y += label_h
        for i, (name, im) in enumerate(tiles):
            x = gap + i * (box[0] + gap)
            sheet.paste(im, (x + (box[0] - im.width) // 2, y + row_h - im.height))
            draw.text((x, y + row_h + 6), name[:44], fill="#e6e9ec", font=font)
        y += row_h + label_h + gap
    sheet.save(path, quality=88)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--face", required=True, help="face folder with refs/ and an optional profile.md")
    ap.add_argument("--look", help="the refs/<look>/ folder to use (default: the only look, or 'default look:' in profile.md)")
    ap.add_argument("--prompt", action="append", required=True, help="one variation: expression, pose, scene. repeat for more")
    ap.add_argument("--count", type=int, default=1, help="images per prompt (default 1)")
    ap.add_argument("--ref", action="append", default=[], help="use these reference photos instead of the look's whole folder")
    ap.add_argument("--aspect", choices=FRAMING, default="landscape")
    ap.add_argument("--framing", help="replace the default framing line")
    ap.add_argument("--backdrop", default="flat solid mid-gray studio background", help="the scene behind the person")
    ap.add_argument("--asset", default="youtube thumbnail photo", help="where the image will be used")
    ap.add_argument("--out", help="output folder (default: <face>/variations/<date>-<look>-<first prompt>)")
    ap.add_argument("--parallel", type=int, default=3, help="codex runs at the same time (default 3)")
    ap.add_argument("--dry-run", action="store_true", help="print the prompts and stop. costs nothing")
    ap.add_argument("--no-tag", action="store_true", help="do not add the new images to the face catalog")
    args = ap.parse_args()

    face = Path(args.face).expanduser().resolve()
    if not face.is_dir():
        sys.exit(f"face folder not found: {face}")
    look = pick_look(face, args.look)
    refs = list_refs(face, look, args.ref)
    if len(refs) < 5:
        print(f"note: only {len(refs)} reference photo(s). likeness is better with 8-12 (see SKILL.md).", file=sys.stderr)

    default_out = face / "variations" / "-".join(filter(None, [str(dt.date.today()), look, slug(args.prompt[0], 30)]))
    out = Path(args.out).expanduser().resolve() if args.out else default_out
    jobs = []
    for p_i, text in enumerate(args.prompt, 1):
        prompt = PROMPT.format(
            asset=args.asset,
            images="Image 1 is an identity reference" if len(refs) == 1 else f"Image 1 to Image {len(refs)} are identity references",
            name=person_name(face),
            profile=identity_lines(face, look),
            prompt=text,
            framing=args.framing or FRAMING[args.aspect],
            backdrop=args.backdrop,
        )
        for c_i in range(1, args.count + 1):
            name = f"{p_i:02d}-{slug(text)}" + (f"-{c_i}" if args.count > 1 else "") + ".png"
            jobs.append({"variation": text, "prompt": prompt, "out_file": str(out / name)})

    if args.dry_run:
        print(f"look: {look or '(none)'}")
        print(f"refs ({len(refs)}): " + ", ".join(str(r) for r in refs))
        print(f"out: {out}\n")
        for job in jobs:
            print(f"--- {Path(job['out_file']).name}\n{job['prompt']}")
        return

    if not shutil.which("codex"):
        sys.exit("codex is not installed. install the codex cli and sign in with chatgpt first.")
    out.mkdir(parents=True, exist_ok=True)
    workdir = Path(tempfile.mkdtemp(prefix="face-variations-"))
    print(f"generating {len(jobs)} image(s) from {len(refs)} reference photo(s), {args.parallel} at a time...", file=sys.stderr)

    results = []
    with cf.ThreadPoolExecutor(max_workers=max(1, args.parallel)) as pool:
        futures = [pool.submit(run_one, job, refs, workdir) for job in jobs]
        for future in cf.as_completed(futures):
            r = future.result()
            results.append(r)
            status = "ok  " if r["ok"] else "FAIL"
            print(f"{status} {Path(r['out_file']).name} ({r['seconds']}s){'' if r['ok'] else ': ' + r['error']}", file=sys.stderr)
    shutil.rmtree(workdir, ignore_errors=True)

    results.sort(key=lambda r: r["out_file"])
    manifest = {
        "created": dt.datetime.now().isoformat(timespec="seconds"),
        "face": str(face),
        "look": look,
        "refs": [str(r) for r in refs],
        "results": results,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    contact_sheet(refs, results, out / "contact-sheet.jpg")

    ok = sum(r["ok"] for r in results)
    print(f"\n{ok}/{len(results)} image(s) in {out}")
    print(f"contact sheet: {out / 'contact-sheet.jpg'}")

    # new images inside the face library go into its catalog right away, so they can be filtered like the rest
    made = [Path(r["out_file"]) for r in results if r["ok"]]
    if made and not args.no_tag and out.is_relative_to(face):
        print("tagging the new image(s) for the catalog...", file=sys.stderr)
        catalog_tag(face, [], retag=False, parallel=args.parallel, model=None, only=made)
    sys.exit(0 if ok == len(results) else 1)


if __name__ == "__main__":
    main()
