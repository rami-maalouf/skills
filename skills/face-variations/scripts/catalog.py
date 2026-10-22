# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow"]
# ///
"""tag every image of a person with a fixed vocabulary, then filter and mix them.

codex looks at each image (`codex exec` with a json schema, on the chatgpt plan) and fills the fields below.
the catalog is <face>/catalog.json. only new or changed images are sent; a moved file keeps its tags.

images it covers: <face>/refs, <face>/approved, <face>/variations, and every folder named on a
"source photos:" line in <face>/profile.md (or given with --photos).

usage:
  uv run catalog.py tag     --face design/faces/rami              # tag new and changed images
  uv run catalog.py find    --face design/faces/rami --where glasses=glasses --where hands=pointing-up,pointing-up-both-hands
  uv run catalog.py find    --face design/faces/rami --where expression=smile --sheet /tmp/smiles.jpg
  uv run catalog.py summary --face design/faces/rami              # how many images have each value
  uv run catalog.py fields                                        # the vocabulary
  uv run catalog.py finder  --face design/faces/rami              # copy the tags to finder tags on the source photos
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
SKIP_NAMES = re.compile(r"^(contact-sheet|.*compare).*", re.IGNORECASE)
TIMEOUT_S = 300

# one: exactly one value. many: every value that applies. left and right are from the viewer's side.
FIELDS: dict[str, tuple[str, list[str]]] = {
    "expression": (
        "many",
        [
            "neutral",
            "calm",
            "smile",
            "teeth-smile",
            "big-grin",
            "laughing",
            "smirk",
            "surprised",
            "shocked",
            "fear",
            "worried",
            "skeptical",
            "confused",
            "thinking",
            "serious",
            "confident",
            "excited",
            "playful",
            "sad",
            "angry",
            "disgusted",
        ],
    ),
    "mouth": ("one", ["closed", "slightly-open", "open", "o-shape", "teeth-showing"]),
    "eyes": ("one", ["normal", "wide", "narrowed", "closed"]),
    "eyebrows": ("one", ["neutral", "raised", "one-raised", "furrowed"]),
    "gaze": ("one", ["camera", "away-left", "away-right", "up", "down"]),
    "head": (
        "many",
        [
            "front",
            "three-quarter-left",
            "three-quarter-right",
            "profile-left",
            "profile-right",
            "tilted-left",
            "tilted-right",
            "chin-down",
            "chin-up",
        ],
    ),
    "hands": (
        "many",
        [
            "none",
            "pointing-up",
            "pointing-up-both-hands",
            "pointing-at-camera",
            "pointing-left",
            "pointing-right",
            "pointing-at-self",
            "pointing-down",
            "hand-on-chin",
            "fist-on-chin",
            "hand-on-mouth",
            "fingers-on-lips",
            "hands-on-head",
            "open-palm",
            "palms-up",
            "wave",
            "thumbs-up",
            "holding-phone",
            "holding-object",
            "arms-crossed",
            "other",
        ],
    ),
    "facial_hair": ("one", ["clean-shaven", "stubble", "mustache-only", "short-beard", "full-beard"]),
    "glasses": ("one", ["none", "glasses", "sunglasses"]),
    "hair": (
        "many",
        ["curly", "wavy", "straight", "high-volume", "curls-over-forehead", "messy", "tidy", "short", "medium-length", "long"],
    ),
    "framing": ("one", ["close-up", "head-and-shoulders", "chest-up", "waist-up", "full-body"]),
    "lighting": (
        "many",
        ["warm-indoor", "cool-indoor", "daylight", "studio", "colored-teal", "colored-purple", "colored-orange", "low-key", "high-key"],
    ),
    "background_type": ("one", ["plain-wall", "room", "studio-backdrop", "solid-color", "gradient", "transparent", "outdoor", "graphic"]),
    "quality": ("many", ["sharp", "soft-focus", "low-resolution", "motion-blur", "noisy", "text-overlay"]),
}
FREE_TEXT = {
    "description": "one plain sentence about the expression, pose and gesture",
    "clothing": "a few words, for example 'dark gray t-shirt with a small logo'",
    "background": "a few words, for example 'beige wall with a wall logo'",
}
FREE_LISTS = {
    "props": "objects the person holds or uses, else []",
    "extra_tags": "up to 5 short lowercase tags for anything useful that the fields miss, else []",
}

PROMPT = """You tag photos of one person for a searchable photo catalog. Look only at Image 1. Do not run any commands.
Fill every field of the output schema with what is clearly visible:
- left and right are from the viewer's side of the image
- expression: 1 to 3 values, the strongest first
- head, hands, hair, lighting, quality: every value that applies. hands is ["none"] when no hand gesture is visible
- description: {description}
- clothing: {clothing}
- background: {background}
- props: {props}
- extra_tags: {extra_tags}
"""


def schema() -> dict:
    props: dict = {}
    for name, (kind, values) in FIELDS.items():
        item = {"type": "string", "enum": values}
        props[name] = {"type": "array", "items": item} if kind == "many" else item
    for name in FREE_TEXT:
        props[name] = {"type": "string"}
    for name in FREE_LISTS:
        props[name] = {"type": "array", "items": {"type": "string"}}
    return {"type": "object", "additionalProperties": False, "required": list(props), "properties": props}


# catalog file and paths


def catalog_path(face: Path) -> Path:
    return face / "catalog.json"


def load(face: Path) -> dict:
    path = catalog_path(face)
    return json.loads(path.read_text()) if path.is_file() else {"version": 1, "images": []}


def save(face: Path, cat: dict) -> None:
    cat["images"].sort(key=lambda r: r["path"])
    catalog_path(face).write_text(json.dumps(cat, indent=1, ensure_ascii=False) + "\n")


def to_key(path: Path, face: Path) -> str:
    # library files are stored relative to the face folder, everything else relative to home
    try:
        return path.relative_to(face).as_posix()
    except ValueError:
        try:
            return "~/" + path.relative_to(Path.home()).as_posix()
        except ValueError:
            return path.as_posix()


def from_key(key: str, face: Path) -> Path:
    if key.startswith("~/"):
        return Path.home() / key[2:]
    return Path(key) if key.startswith("/") else face / key


def photo_roots(face: Path, extra: list[str]) -> list[Path]:
    roots = [Path(p).expanduser() for p in extra]
    profile = face / "profile.md"
    if profile.is_file():
        for line in profile.read_text().splitlines():
            if line.lower().startswith("source photos:"):
                roots += [Path(p).expanduser() for p in re.findall(r"`([^`]+)`", line) if "/" in p]
    return roots


def scan(face: Path, extra: list[str]) -> list[tuple[Path, str, Path]]:
    """every image to catalog: (file, kind, the root it was found under)."""
    found = []
    for sub, kind in (("refs", "ref"), ("approved", "approved"), ("variations", "generated")):
        root = face / sub
        found += [(p, kind, root) for p in sorted(root.rglob("*")) if root.is_dir() and p.is_file()]
    for root in photo_roots(face, extra):
        if root.is_dir():
            found += [(p, "photo", root) for p in sorted(root.rglob("*")) if p.is_file()]
        else:
            print(f"note: source photos folder not here, its entries stay as they are: {root}", file=sys.stderr)
    return [(p, k, r) for p, k, r in found if p.suffix.lower() in IMAGE_EXTS and not SKIP_NAMES.match(p.stem)]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def look_dates(face: Path) -> dict[str, str]:
    """date -> look, from 'photos taken:' lines under '## look: <name>' in profile.md."""
    profile = face / "profile.md"
    dates, look = {}, None
    if profile.is_file():
        for line in profile.read_text().splitlines():
            if line.startswith("## "):
                look = line[len("## look:") :].strip() if line.lower().startswith("## look:") else None
            elif look and line.lower().startswith("photos taken:"):
                dates |= dict.fromkeys(re.findall(r"\d{4}-\d{2}-\d{2}", line), look)
    return dates


def look_of(path: Path, kind: str, face: Path, taken: str, dates: dict[str, str]) -> str | None:
    if kind in ("photo", "approved"):
        return dates.get(taken)
    if kind == "ref":
        rel = path.relative_to(face / "refs").parts
        return rel[0] if len(rel) > 1 else None
    if kind == "generated":
        manifest = path.parent / "manifest.json"
        if manifest.is_file():
            return json.loads(manifest.read_text()).get("look")
    return None


def image_facts(path: Path) -> dict:
    with Image.open(path) as im:
        exif = im.getexif()
        taken = exif.get_ifd(0x8769).get(36867) or exif.get(306)
        size = ImageOps.exif_transpose(im).size
    if taken:
        taken = taken[:10].replace(":", "-")
    else:
        taken = dt.date.fromtimestamp(path.stat().st_mtime).isoformat()
    return {"width": size[0], "height": size[1], "taken": taken}


# tagging


def ask_codex(path: Path, schema_file: Path, workdir: Path, model: str | None) -> dict:
    last = Path(tempfile.mkstemp(suffix=".json", dir=workdir)[1])
    cmd = ["codex", "exec", "--skip-git-repo-check", "-s", "read-only", "--output-schema", str(schema_file), "-o", str(last)]
    if model:
        cmd += ["-m", model]
    cmd.append(f"--image={path}")
    prompt = PROMPT.format(**FREE_TEXT, **FREE_LISTS)
    proc = subprocess.run(cmd, check=False, input=prompt, capture_output=True, text=True, timeout=TIMEOUT_S)
    text = last.read_text().strip() if last.is_file() else ""
    if proc.returncode != 0 or not text:
        raise RuntimeError(f"codex exit {proc.returncode}: {' '.join((proc.stderr or '').strip().splitlines()[-2:])}")
    tags = json.loads(text)
    for name, (kind, values) in FIELDS.items():
        got = tags.get(name)
        bad = [v for v in (got if kind == "many" else [got]) if v not in values]
        if bad:
            raise RuntimeError(f"unknown {name} value(s): {bad}")
    return tags


def tag(face: Path, extra: list[str], retag: bool, parallel: int, model: str | None, only: list[Path] | None = None) -> int:
    cat = load(face)
    by_path = {r["path"]: r for r in cat["images"]}
    by_hash = {r["sha256"]: r for r in cat["images"]}
    files = scan(face, extra)
    dates = look_dates(face)
    if only is not None:
        wanted = {p.resolve() for p in only}
        files = [f for f in files if f[0].resolve() in wanted]
    scanned_roots = {to_key(r, face) for _, _, r in files} | {to_key(face / s, face) for s in ("refs", "approved", "variations")}

    keep, todo, copies = [], [], []
    seen, pending = set(), set()
    for path, kind, _root in files:
        key = to_key(path, face)
        seen.add(key)
        digest = sha256(path)
        facts = image_facts(path)
        base = {"path": key, "kind": kind, "look": look_of(path, kind, face, facts["taken"], dates), "sha256": digest, **facts}
        old = by_path.get(key) or by_hash.get(digest)
        if old and old["sha256"] == digest and not retag:
            keep.append({**old, **base})
        elif digest in pending:
            copies.append(base)  # the same file twice: tag it once, copy the tags
        else:
            pending.add(digest)
            todo.append((path, base))

    # entries whose file is gone from a scanned folder are dropped; entries from folders not on this machine stay
    for r in cat["images"]:
        if r["path"] in seen:
            continue
        gone_from_scanned = any(r["path"].startswith(root.rstrip("/") + "/") for root in scanned_roots)
        if only is not None or not gone_from_scanned:
            keep.append(r)

    if todo and not shutil.which("codex"):
        sys.exit("codex is not installed. install the codex cli and sign in with chatgpt first.")
    print(f"{len(keep)} image(s) already tagged, {len(todo)} to tag", file=sys.stderr)

    failed = 0
    if todo:
        workdir = Path(tempfile.mkdtemp(prefix="face-catalog-"))
        schema_file = workdir / "schema.json"
        schema_file.write_text(json.dumps(schema()))
        with cf.ThreadPoolExecutor(max_workers=max(1, parallel)) as pool:
            futures = {pool.submit(ask_codex, path, schema_file, workdir, model): (path, base) for path, base in todo}
            for future in cf.as_completed(futures):
                path, base = futures[future]
                try:
                    tags = future.result()
                except Exception as err:  # noqa: BLE001 - one bad image must not stop the batch
                    failed += 1
                    print(f"FAIL {base['path']}: {err}", file=sys.stderr)
                    continue
                keep.append({**base, "tagged": dt.date.today().isoformat(), **tags})
                print(f"ok   {base['path']}: {', '.join(tags['expression'])}; hands {', '.join(tags['hands'])}", file=sys.stderr)
        shutil.rmtree(workdir, ignore_errors=True)

    tagged = {r["sha256"]: r for r in keep}
    keep += [{**tagged[c["sha256"]], **c} for c in copies if c["sha256"] in tagged]
    cat["images"] = keep
    save(face, cat)
    outliers = look_outliers(keep)
    for line in outliers:
        print(f"check {line}", file=sys.stderr)
    if outliers:
        print("fix a wrong tag with: catalog.py set --face <face> <path> field=value", file=sys.stderr)
    print(f"{len(keep)} image(s) in {catalog_path(face)}{f', {failed} failed' if failed else ''}")
    return 1 if failed else 0


def look_outliers(records: list[dict]) -> list[str]:
    """images whose facial hair or glasses differ from most images of the same look: often a tagging mistake."""
    out = []
    for field in ("facial_hair", "glasses"):
        by_look: dict[str, list[dict]] = {}
        for r in records:
            if r.get("look"):
                by_look.setdefault(r["look"], []).append(r)
        for look, group in by_look.items():
            values = [r.get(field) for r in group]
            common = max(set(values), key=values.count)
            out += [f"{r['path']}: {field} is {r.get(field)}, most {look} images say {common}" for r in group if r.get(field) != common]
    return out


def set_tags(face: Path, target: str, changes: list[str]) -> None:
    cat = load(face)
    hits = [r for r in cat["images"] if r["path"] == target or r["path"].endswith(target)]
    if len(hits) != 1:
        sys.exit(f"'{target}' matches {len(hits)} images. give more of the path.")
    record = hits[0]
    for change in changes:
        name, _, value = change.partition("=")
        if name in FIELDS:
            kind, allowed = FIELDS[name]
            values = [v.strip() for v in value.split(",")]
            bad = [v for v in values if v not in allowed]
            if bad:
                sys.exit(f"{name} has no value {bad}. allowed: {', '.join(allowed)}")
            record[name] = values if kind == "many" else values[0]
        elif name in (*FREE_TEXT, "look"):
            record[name] = value
        elif name in FREE_LISTS:
            record[name] = [v.strip() for v in value.split(",") if v.strip()]
        else:
            sys.exit(f"unknown field '{name}'. see: catalog.py fields")
    record["edited"] = dt.date.today().isoformat()
    save(face, cat)
    print(f"updated {record['path']}")


# filtering


def parse_where(items: list[str]) -> list[tuple[str, set[str]]]:
    out = []
    for item in items:
        name, _, values = item.partition("=")
        if not values:
            sys.exit(f"--where needs field=value, got '{item}'")
        out.append((name.strip(), {v.strip() for v in values.split(",")}))
    return out


def matches(record: dict, where: list[tuple[str, set[str]]], exclude: list[tuple[str, set[str]]], text: list[str]) -> bool:
    def has(name: str, values: set[str]) -> bool:
        got = record.get(name)
        got = got if isinstance(got, list) else [got]
        return any(str(g) in values for g in got if g is not None)

    if not all(has(n, v) for n, v in where):
        return False
    if any(has(n, v) for n, v in exclude):
        return False
    blob = " ".join(str(record.get(k, "")) for k in ("description", "clothing", "background", "props", "extra_tags")).lower()
    return all(t.lower() in blob for t in text)


def sheet(records: list[dict], face: Path, out: Path) -> None:
    box, gap, label_h, cols = (300, 300), 10, 46, 6
    font = ImageFont.load_default(size=15)
    tiles = []
    for r in records:
        try:
            im = ImageOps.contain(ImageOps.exif_transpose(Image.open(from_key(r["path"], face))).convert("RGB"), box)
        except OSError:
            continue
        # mac photo booth names have a narrow space before am/pm that the default font cannot draw
        name = Path(r["path"]).name.replace("\u202f", " ")
        tiles.append((im, name, ", ".join(r.get("expression", [])[:2])))
    rows = [tiles[i : i + cols] for i in range(0, len(tiles), cols)] or [[]]
    heights = [max((im.height for im, _, _ in row), default=0) for row in rows]
    width = gap + min(cols, max(1, len(tiles))) * (box[0] + gap)
    canvas = Image.new("RGB", (width, gap + sum(h + label_h + gap for h in heights)), "#141518")
    draw = ImageDraw.Draw(canvas)
    y = gap
    for row, row_h in zip(rows, heights):
        for i, (im, name, expression) in enumerate(row):
            x = gap + i * (box[0] + gap)
            canvas.paste(im, (x + (box[0] - im.width) // 2, y + row_h - im.height))
            draw.text((x, y + row_h + 4), name[:38], fill="#e6e9ec", font=font)
            draw.text((x, y + row_h + 23), expression[:38], fill="#9aa3ad", font=font)
        y += row_h + label_h + gap
    canvas.save(out, quality=86)


def finder_tags(face: Path, kinds: set[str], clear: bool) -> None:
    # finder tags live in an extended attribute: a binary plist of strings. spotlight and finder search read them
    count = 0
    for r in load(face)["images"]:
        if r["kind"] not in kinds:
            continue
        path = from_key(r["path"], face)
        if not path.is_file():
            continue
        if clear:
            subprocess.run(["xattr", "-d", "com.apple.metadata:_kMDItemUserTags", str(path)], check=False, capture_output=True)
        else:
            values = [
                *r.get("expression", []),
                *[h for h in r.get("hands", []) if h != "none"],
                r.get("facial_hair"),
                *([r["glasses"]] if r.get("glasses") not in (None, "none") else []),
                *r.get("head", []),
                r.get("framing"),
            ]
            names = list(dict.fromkeys(v for v in values if v))
            data = plistlib.dumps(names, fmt=plistlib.FMT_BINARY).hex()
            subprocess.run(["xattr", "-wx", "com.apple.metadata:_kMDItemUserTags", data, str(path)], check=True)
        count += 1
    print(f"{'cleared' if clear else 'wrote'} finder tags on {count} file(s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("tag", help="tag new and changed images")
    t.add_argument("--face", required=True)
    t.add_argument("--photos", action="append", default=[], help="another folder of source photos")
    t.add_argument("--retag", action="store_true", help="tag every image again")
    t.add_argument("--parallel", type=int, default=4)
    t.add_argument("--model", help="codex model to use (default: the codex default)")

    f = sub.add_parser("find", help="list images that match")
    f.add_argument("--face", required=True)
    f.add_argument("--where", action="append", default=[], help="field=value[,value]: keep images with any of the values")
    f.add_argument("--not", dest="exclude", action="append", default=[], help="field=value[,value]: drop images with any of them")
    f.add_argument("--text", action="append", default=[], help="a word that must be in the description, clothing, background or tags")
    f.add_argument("--sheet", help="also write a contact sheet of the matches to this jpg")
    f.add_argument("--json", action="store_true", help="print the full records")

    s = sub.add_parser("summary", help="count the images per field value")
    s.add_argument("--face", required=True)
    s.add_argument("--where", action="append", default=[])

    sub.add_parser("fields", help="print the vocabulary")

    se = sub.add_parser("set", help="fix tags by hand. --retag overwrites hand fixes")
    se.add_argument("--face", required=True)
    se.add_argument("path", help="the image's catalog path, or its end")
    se.add_argument("changes", nargs="+", help="field=value[,value]")

    fi = sub.add_parser("finder", help="copy the tags to finder tags (macos)")
    fi.add_argument("--face", required=True)
    fi.add_argument("--kind", action="append", default=[], help="photo, ref, generated, approved (default: photo)")
    fi.add_argument("--clear", action="store_true", help="remove the finder tags again")

    args = ap.parse_args()

    if args.cmd == "fields":
        for name, (kind, values) in FIELDS.items():
            print(f"{name} ({kind}): {', '.join(values)}")
        print("also: kind (photo, ref, generated, approved), look, taken, " + ", ".join([*FREE_TEXT, *FREE_LISTS]))
        return

    face = Path(args.face).expanduser().resolve()
    if not face.is_dir():
        sys.exit(f"face folder not found: {face}")

    if args.cmd == "tag":
        sys.exit(tag(face, args.photos, args.retag, args.parallel, args.model))

    if args.cmd == "set":
        set_tags(face, args.path, args.changes)
        return

    if args.cmd == "finder":
        finder_tags(face, set(args.kind or ["photo"]), args.clear)
        return

    records = load(face)["images"]
    if not records:
        sys.exit(f"no catalog yet. run: uv run catalog.py tag --face {args.face}")
    where = parse_where(args.where)

    if args.cmd == "summary":
        records = [r for r in records if matches(r, where, [], [])]
        print(f"{len(records)} image(s)")
        for name in ["kind", "look", *FIELDS]:
            counts: dict[str, int] = {}
            for r in records:
                got = r.get(name)
                for v in got if isinstance(got, list) else [got]:
                    counts[str(v)] = counts.get(str(v), 0) + 1
            print(f"{name}: " + ", ".join(f"{v} {n}" for v, n in sorted(counts.items(), key=lambda kv: -kv[1])))
        return

    hits = [r for r in records if matches(r, where, parse_where(args.exclude), args.text)]
    for r in hits:
        print(json.dumps(r, ensure_ascii=False) if args.json else from_key(r["path"], face))
    print(f"{len(hits)} match(es)", file=sys.stderr)
    if args.sheet and hits:
        sheet(hits, face, Path(args.sheet).expanduser())
        print(f"sheet: {args.sheet}", file=sys.stderr)


if __name__ == "__main__":
    main()
