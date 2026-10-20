#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["beautifulsoup4>=4.12"]
# ///
"""
extract.py - pull readable paragraphs out of a web page or html file.

Usage:
    uv run extract.py <url-or-html-file> --list-anchors
    uv run extract.py <url-or-html-file> -o source.txt
    uv run extract.py <url-or-html-file> --start CHAPTER_TWO_ --end CHAPTER_FOUR_ -o source.txt

--start / --end take an anchor (an element's id or name attribute, the part after
"#" in a url). the text starts at --start and stops right before --end. without
them the whole page body is used. output: one paragraph per block, blank line between.
"""

import argparse
import re
import sys
import urllib.request

from bs4 import BeautifulSoup

BLOCKS = ["p", "h1", "h2", "h3", "h4", "h5", "h6", "li", "blockquote"]


def load(src: str) -> str:
    if re.match(r"https?://", src):
        req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.read().decode(r.headers.get_content_charset() or "utf-8", errors="replace")
    return open(src, encoding="utf-8", errors="replace").read()


def anchor_pos(html: str, anchor: str) -> int:
    m = re.search(r'(?:id|name)\s*=\s*["\']' + re.escape(anchor) + r'["\']', html)
    if not m:
        sys.exit(f"anchor not found: {anchor} (run with --list-anchors)")
    # back up to the block that holds the anchor, so its heading text is kept
    tag = html.rfind("<", 0, m.start())
    blocks = list(re.finditer(r"<(?:p|h[1-6]|li|blockquote)\b", html[:tag]))
    if blocks:
        block = blocks[-1].start()
        # only use it if that block is still open, i.e. not closed before the anchor
        if not re.search(r"</(?:p|h[1-6]|li|blockquote)>", html[block:tag]):
            return block
    return tag


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("--start")
    ap.add_argument("--end")
    ap.add_argument("--list-anchors", action="store_true")
    ap.add_argument("-o", "--out", default="-")
    a = ap.parse_args()

    html = load(a.src)

    if a.list_anchors:
        soup = BeautifulSoup(html, "html.parser")
        # meta tags in <head> also carry name attributes, so only look at the body
        soup = soup.body or soup
        seen = set()
        for el in soup.find_all(lambda t: t.has_attr("id") or (t.name == "a" and t.has_attr("name"))):
            key = el.get("id") or el.get("name")
            if key in seen or el.name in ("script", "style", "input", "form", "button"):
                continue
            seen.add(key)
            label = " ".join(el.get_text(" ").split())
            if not label:
                nxt = el.find_next(string=lambda s: s and s.strip())
                label = " ".join(str(nxt or "").split())
            # skip footnote markers like [12] and containers that wrap page chrome
            if re.fullmatch(r"\[?\d+\]?", label) or len(label) > 120:
                continue
            print(f"{key}\t{label[:70]}")
        return

    start = anchor_pos(html, a.start) if a.start else 0
    end = anchor_pos(html, a.end) if a.end else len(html)
    if end <= start:
        sys.exit("--end comes before --start")
    soup = BeautifulSoup(html[start:end], "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "sup"]):
        tag.decompose()

    out = []
    for el in soup.find_all(BLOCKS):
        # skip containers whose text is already emitted by a nested block
        if el.find(BLOCKS):
            continue
        t = " ".join(el.get_text(" ").split())
        if t:
            out.append(t)
    text = "\n\n".join(out) + "\n"
    if a.out == "-":
        sys.stdout.write(text)
    else:
        open(a.out, "w").write(text)
        print(f"{len(out)} blocks, {len(text.split())} words -> {a.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
