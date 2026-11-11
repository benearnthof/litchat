"""Sentence-level tokenizer: a thin wrapper around NLTK's Punkt tokenizer.

Turns the text of a book into "lines" for the player. Each line is one
sentence. The module is independent of the EPUB parser: the core function
works on plain strings, and `tokenize_book` only expects an object shaped
like the parser's `Book` (chapters -> blocks with `.kind` and `.text`).

    split_sentences(text, language="english")  -> list[str]
    tokenize_book(book, language="english")    -> list[Line]

Requires:  pip install nltk
The Punkt model data is downloaded automatically on first use (one small
download). To fetch it yourself:  python -m nltk.downloader punkt_tab

Notes
-----
* Punkt is a statistical model and knows nothing about dialogue, so a tag
  such as `"Where?" Marco asked.` may be split into two lines.
* Headings are never split; `tokenize_book` emits each as one line.

Usage:
    python tokenizer.py book.epub [--chapter N] [--limit N]
(requires parser.py next to this file for the CLI only)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

import nltk
from nltk.tokenize import sent_tokenize

_WHITESPACE = re.compile(r"\s+")
_data_checked = False


def _ensure_punkt_data() -> None:
    """Make sure the Punkt model is available, downloading it once if not."""
    global _data_checked
    if _data_checked:
        return
    for resource in ("tokenizers/punkt_tab", "tokenizers/punkt"):
        try:
            nltk.data.find(resource)
            _data_checked = True
            return
        except LookupError:
            continue
    if not nltk.download("punkt_tab", quiet=True):
        raise RuntimeError(
            "Could not download the NLTK Punkt data. "
            "Run:  python -m nltk.downloader punkt_tab"
        )
    _data_checked = True


def split_sentences(text: str, *, language: str = "english") -> list[str]:
    """Split `text` into sentences using NLTK's Punkt tokenizer.

    Whitespace is normalised to single spaces. Returns [] for blank input.
    `language` is any language Punkt ships a model for (e.g. "german").
    """
    text = _WHITESPACE.sub(" ", text).strip()
    if not text:
        return []
    _ensure_punkt_data()
    return [s.strip() for s in sent_tokenize(text, language=language) if s.strip()]


@dataclass(frozen=True)
class Line:
    """One line for the player, with enough position info for bookmarks."""

    chapter_index: int
    block_index: int  # index of the source block within the chapter
    kind: str  # "heading" or "sentence"
    text: str


def tokenize_book(book: Any, **options: Any) -> list[Line]:
    """Flatten a parsed book into a list of Lines in reading order.

    `book` is the parser's Book (anything with .chapters, each having .index
    and .blocks of objects with .kind and .text). Headings stay whole; every
    paragraph is split into sentences. `options` go to `split_sentences`.
    """
    lines: list[Line] = []
    for chapter in book.chapters:
        for block_index, block in enumerate(chapter.blocks):
            if block.kind == "heading":
                lines.append(Line(chapter.index, block_index, "heading", block.text))
                continue
            for sentence in split_sentences(block.text, **options):
                lines.append(Line(chapter.index, block_index, "sentence", sentence))
    return lines



def _main(argv: list[str]) -> int:
    import argparse

    ap = argparse.ArgumentParser(description="Preview sentence tokenization of an EPUB.")
    ap.add_argument("epub", help="path to a DRM-free EPUB")
    ap.add_argument("--chapter", type=int, help="only show this chapter index")
    ap.add_argument("--limit", type=int, default=40, help="max lines to print (default 40)")
    ap.add_argument("--language", default="english", help="Punkt language (default english)")
    args = ap.parse_args(argv[1:])

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")  # never crash on odd console encodings

    from parser import EpubError, parse_epub  # the EPUB parser module

    try:
        book = parse_epub(args.epub)
        # print(book)
    except EpubError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    lines = tokenize_book(book, language=args.language)
    shown = [l for l in lines if args.chapter is None or l.chapter_index == args.chapter]

    for l in shown[: args.limit]:
        tag = "H" if l.kind == "heading" else " "
        print(f"[{l.chapter_index:>2}.{l.block_index:<3}]{tag} {l.text}")
    if len(shown) > args.limit:
        print(f"... {len(shown) - args.limit} more lines (use --limit)")

    sentences = [l for l in lines if l.kind == "sentence"]
    long_lines = sum(1 for l in lines if len(l.text) > 500)
    print()
    print(f"Total lines: {len(lines)} ({len(sentences)} sentences)")
    print(f"Lines over 500 characters: {long_lines}")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))