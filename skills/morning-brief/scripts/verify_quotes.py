#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# ///
"""
verify_quotes.py - prove that every quote in the morning brief is word for word.

Usage:
    uv run verify_quotes.py quotes.txt --source "My Ignition Library v2.md" --source night.txt
    printf '%s\n' "quote one" "quote two" | uv run verify_quotes.py - --source a.md

quotes.txt holds one quote per line. a quote passes when it appears in at least
one source after light normalization: markdown emphasis, smart quotes, dash
variants and whitespace are evened out, and case is ignored. words are never
changed. exit code is 0 when all quotes pass, 1 when any quote fails.
"""

import argparse
import re
import sys
from pathlib import Path

# characters that differ between a vault file and a copied quote but never change words
CHAR_MAP = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)


def normalize(text: str) -> str:
    text = text.translate(CHAR_MAP)
    # drop markdown emphasis and wiki-link brackets
    text = re.sub(r"[*_`]", "", text)
    text = text.replace("[[", "").replace("]]", "")
    text = re.sub(r"\s+", " ", text)
    return text.strip().lower()


def strip_wrapping(quote: str) -> str:
    # allow a quote to arrive with its own blockquote marker or surrounding quote marks
    quote = quote.strip()
    quote = re.sub(r"^>\s*", "", quote)
    quote = re.sub(r"^[-*]\s+", "", quote)
    quote = quote.translate(CHAR_MAP)
    if len(quote) >= 2 and quote[0] == quote[-1] and quote[0] in "\"'":
        quote = quote[1:-1]
    return quote


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("quotes", help="file with one quote per line, or - for stdin")
    parser.add_argument("--source", action="append", required=True, help="source file (repeatable)")
    args = parser.parse_args()

    raw = sys.stdin.read() if args.quotes == "-" else Path(args.quotes).read_text(encoding="utf-8")
    quotes = [q for q in (strip_wrapping(line) for line in raw.splitlines()) if q]

    sources = {}
    for path in args.source:
        sources[path] = normalize(Path(path).read_text(encoding="utf-8"))

    failed = 0
    for quote in quotes:
        needle = normalize(quote)
        found = [name for name, text in sources.items() if needle in text]
        if found:
            print(f"ok    {Path(found[0]).name}: {quote}")
        else:
            failed += 1
            print(f"FAIL  not word for word in any source: {quote}")

    print(f"\n{len(quotes) - failed}/{len(quotes)} quotes verified")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
