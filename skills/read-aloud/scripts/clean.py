#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""
clean.py - turn extracted text into a narration script.

Usage:
    uv run clean.py source.txt -o narration.txt
    uv run clean.py source.txt -o narration.txt --keep-numbers --title "Chapter Two."

generic fixes only: drops footnote markers like [12], drops leading paragraph
numbers ("46. "), turns ALL CAPS headings into title case, and ends short
headings with a period so the voice pauses on them. document-specific fixes
(citations, abbreviations, typos) are done by hand on narration.txt afterwards.
"""

import argparse
import re

SMALL = {"a", "an", "and", "as", "at", "but", "by", "for", "in", "of", "on", "or", "the", "to", "with"}
ACRONYMS = {"AI", "UN", "USA", "EU", "UK", "II", "III", "IV", "XIV", "XXIII"}


def title_case(s: str) -> str:
    words = s.lower().split()
    out = []
    for i, w in enumerate(words):
        bare = w.strip(".,:;!?").upper()
        if bare in ACRONYMS:
            out.append(w.upper())
        elif i and w in SMALL:
            out.append(w)
        else:
            out.append(w[:1].upper() + w[1:])
    return " ".join(out)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--keep-numbers", action="store_true", help="keep leading paragraph numbers")
    ap.add_argument("--title", help="line to read first, e.g. 'Chapter Two.'")
    a = ap.parse_args()

    paras = [p.strip() for p in open(a.src).read().split("\n\n") if p.strip()]
    out = [a.title] if a.title else []
    for p in paras:
        p = re.sub(r"\s*\[\d+\]", "", p)
        if not a.keep_numbers:
            p = re.sub(r"^\d+\.\s+", "", p)
        if p.isupper():
            p = title_case(p)
        if len(p) < 110 and not p.endswith((".", "?", "!", "”", '"', ":")):
            p += "."
        out.append(p)
    open(a.out, "w").write("\n\n".join(out) + "\n")
    print(f"{len(out)} paragraphs, {sum(len(p.split()) for p in out)} words -> {a.out}")


if __name__ == "__main__":
    main()
