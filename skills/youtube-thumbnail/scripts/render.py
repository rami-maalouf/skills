# /// script
# requires-python = ">=3.11"
# dependencies = ["playwright==1.58.0", "pillow"]
# ///
"""render 1280x720 html thumbnails to upload-ready images, plus a check sheet that shows each one the way youtube does.

for each <name>.html it writes, next to it (or in --out-dir):
  <name>.png        2560x1440 master
  <name>.jpg        1280x720 upload file, under youtube's 2 mb limit
  check-<name>.png  home feed, search, up next, 120 px glance and mobile views, with the duration badge on top
and when there are 2 or more thumbnails:
  compare.png       all of them side by side as home feed cards

usage:
  uv run render.py thumb-a.html thumb-b.html --title "Title for a" --title "Title for b" --channel Expo --duration 9:41
"""

from __future__ import annotations

import argparse
import html
import io
import sys
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

W, H = 1280, 720
MAX_BYTES = 2 * 1024 * 1024

PAGE = """<!doctype html>
<html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&display=block" rel="stylesheet">
<style>
  * {{ box-sizing: border-box; margin: 0; }}
  body {{ background: #0f0f0f; color: #f1f1f1; font-family: Roboto, Arial, sans-serif; padding: 28px; width: {width}px; }}
  h2 {{ font-size: 13px; font-weight: 500; letter-spacing: .08em; text-transform: uppercase; color: #717171; margin: 0 0 12px; }}
  section {{ margin-bottom: 32px; }}
  .row {{ display: flex; gap: 24px; align-items: flex-start; flex-wrap: wrap; }}
  .thumb {{ position: relative; flex-shrink: 0; border-radius: 12px; overflow: hidden; background: #222; }}
  .thumb img {{ display: block; width: 100%; height: 100%; object-fit: cover; }}
  .badge {{ position: absolute; right: 6px; bottom: 6px; padding: 1px 4px; border-radius: 4px; background: rgba(0,0,0,.8);
            color: #fff; font-size: 12px; font-weight: 500; line-height: 18px; }}
  .card {{ width: var(--w); }}
  .card .thumb {{ width: var(--w); height: calc(var(--w) * 9 / 16); }}
  .meta {{ display: flex; gap: 12px; margin-top: 12px; }}
  .avatar {{ width: 36px; height: 36px; border-radius: 50%; background: #3f3f3f; flex-shrink: 0; }}
  .title {{ font-size: 16px; font-weight: 500; line-height: 22px; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
  .sub {{ font-size: 14px; color: #aaa; margin-top: 4px; line-height: 20px; }}
  .search {{ display: flex; gap: 16px; width: 1000px; }}
  .search .thumb {{ width: 360px; height: 202px; }}
  .search .title {{ font-size: 18px; line-height: 26px; font-weight: 400; }}
  .next {{ display: flex; gap: 8px; width: 402px; }}
  .next .thumb {{ width: 168px; height: 94px; border-radius: 8px; }}
  .next .title {{ font-size: 14px; line-height: 20px; }}
  .next .sub {{ font-size: 12px; }}
  .glance .thumb {{ width: 120px; height: 68px; border-radius: 6px; }}
  .mobile {{ width: 412px; background: #0f0f0f; }}
  .mobile .thumb {{ width: 412px; height: 232px; border-radius: 0; }}
  .mobile .meta {{ padding: 0 12px; }}
  .mobile .title {{ font-size: 14px; line-height: 20px; }}
</style></head>
<body>{body}</body></html>"""


def thumb(src: str, duration: str, badge: bool = True) -> str:
    return f'<div class="thumb"><img src="{src}">' + (f'<span class="badge">{html.escape(duration)}</span>' if badge else "") + "</div>"


def meta(title: str, channel: str, avatar: bool = True) -> str:
    av = '<div class="avatar"></div>' if avatar else ""
    return (
        f'<div class="meta">{av}<div><div class="title">{html.escape(title)}</div>'
        f'<div class="sub">{html.escape(channel)} · 12K views · 2 days ago</div></div></div>'
    )


def check_body(src: str, title: str, channel: str, duration: str) -> str:
    return (
        '<section><h2>home feed (desktop)</h2><div class="row">'
        f'<div class="card" style="--w:360px">{thumb(src, duration)}{meta(title, channel)}</div>'
        f'<div class="card" style="--w:300px">{thumb(src, duration)}{meta(title, channel)}</div></div></section>'
        f'<section><h2>search result</h2><div class="search">{thumb(src, duration)}'
        f'<div><div class="title">{html.escape(title)}</div><div class="sub">12K views · 2 days ago</div>'
        f'<div class="sub">{html.escape(channel)}</div></div></div></section>'
        '<section><h2>up next and glance test (120 px)</h2><div class="row">'
        f'<div class="next">{thumb(src, duration)}<div><div class="title">{html.escape(title)}</div>'
        f'<div class="sub">{html.escape(channel)}</div><div class="sub">12K views</div></div></div>'
        f'<div class="glance">{thumb(src, duration, badge=False)}</div></div></section>'
        f'<section><h2>mobile home feed</h2><div class="mobile">{thumb(src, duration)}{meta(title, channel)}</div></section>'
    )


def save_jpg(png: Path, jpg: Path) -> int:
    im = Image.open(png).convert("RGB").resize((W, H), Image.LANCZOS)
    for quality in (95, 92, 88, 84, 80, 75, 70):
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=quality, optimize=True, progressive=True)
        if buf.tell() <= MAX_BYTES:
            break
    jpg.write_bytes(buf.getvalue())
    return buf.tell()


def screenshot(page, body: str, width: int, out: Path) -> None:
    # a page on disk, so it may load the local thumbnail images
    tmp = out.with_name(f".{out.stem}.html")
    tmp.write_text(PAGE.format(width=width, body=body))
    # a short viewport, so the full-page screenshot is only as tall as the content
    page.set_viewport_size({"width": width, "height": 100})
    page.goto(tmp.as_uri(), wait_until="networkidle")
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(out), full_page=True)
    tmp.unlink()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("html", nargs="+", help="1280x720 thumbnail html files")
    ap.add_argument("--title", action="append", default=[], help="video title per html, in the same order (one title is used for all)")
    ap.add_argument("--channel", default="Channel name", help="channel name for the feed mock")
    ap.add_argument("--duration", default="10:24", help="video length shown in the bottom-right badge")
    ap.add_argument("--out-dir", help="write here instead of next to each html")
    args = ap.parse_args()

    files = [Path(p).resolve() for p in args.html]
    for f in files:
        if not f.is_file():
            sys.exit(f"not found: {f}")
    titles = args.title or ["Video title goes here"]
    if len(titles) not in (1, len(files)):
        sys.exit("give one --title for all thumbnails, or one per html file")
    titles = titles * len(files) if len(titles) == 1 else titles

    cards = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        shot = browser.new_page(viewport={"width": W, "height": H}, device_scale_factor=2)
        sheet = browser.new_page(device_scale_factor=2)
        for f, title in zip(files, titles):
            out = Path(args.out_dir).resolve() if args.out_dir else f.parent
            out.mkdir(parents=True, exist_ok=True)
            png, jpg, check = out / f"{f.stem}.png", out / f"{f.stem}.jpg", out / f"check-{f.stem}.png"

            shot.goto(f.as_uri(), wait_until="networkidle")
            shot.evaluate("document.fonts.ready")
            size = shot.evaluate("[document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
            if size != [W, H]:
                print(f"warn {f.name}: page is {size[0]}x{size[1]}, expected {W}x{H}. check the layout for overflow.", file=sys.stderr)
            shot.screenshot(path=str(png), clip={"x": 0, "y": 0, "width": W, "height": H})
            n_bytes = save_jpg(png, jpg)

            screenshot(sheet, check_body(png.as_uri(), title, args.channel, args.duration), 1080, check)
            cards.append(
                f'<div class="card" style="--w:420px">{thumb(png.as_uri(), args.duration)}{meta(title, args.channel)}'
                f'<div class="sub" style="margin-left:48px">{html.escape(f.stem)}</div></div>'
            )
            print(f"ok {f.name}: {jpg} ({n_bytes / 1024:.0f} KB), {check}")

        if len(files) > 1:
            out = Path(args.out_dir).resolve() if args.out_dir else files[0].parent
            compare = out / "compare.png"
            screenshot(sheet, f'<section><h2>compare</h2><div class="row">{"".join(cards)}</div></section>', 940, compare)
            print(f"ok compare: {compare}")
        browser.close()


if __name__ == "__main__":
    main()
