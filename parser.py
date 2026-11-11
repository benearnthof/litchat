"""Minimal EPUB parser.

Takes the path to a DRM-free EPUB and returns a structured Book:

    Book
      title, author, language
      chapters: list[Chapter]
        title, href, index
        blocks: list[Block]
          kind: "heading" | "paragraph"
          text: cleaned, whitespace-normalized text

Standard library only. Sentence splitting, chatter attribution, etc. are
intentionally left to downstream stages.

Usage:
    python parser.py book.epub            # print a summary
    python parser.py book.epub --json     # dump the full structure as JSON
"""

from __future__ import annotations

import json
import posixpath
import re
import sys
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from html.parser import HTMLParser
from urllib.parse import unquote, urldefrag
from xml.etree import ElementTree as ET


class EpubError(Exception):
    """Raised when file is corrupt/copyright protected."""


@dataclass
class Block:
    kind: str  # "heading" or "paragraph"
    text: str


@dataclass
class Chapter:
    index: int
    href: str
    title: str | None
    blocks: list[Block] = field(default_factory=list)

    @property
    def paragraphs(self) -> list[str]:
        """Body text only (headings excluded)."""
        return [b.text for b in self.blocks if b.kind == "paragraph"]


@dataclass
class Book:
    title: str | None
    author: str | None
    language: str | None
    chapters: list[Chapter] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


# xhtml tags
_HEADING_TAGS = {"h1", "h2", "h3", "h4", "h5", "h6"}
_BLOCK_TAGS = {
    "p", "div", "li", "blockquote", "pre", "section", "article", "aside",
    "tr", "dt", "dd", "figcaption", "caption", "ul", "ol", "table", "hr",
    "body",
} | _HEADING_TAGS
_SKIP_TAGS = {"script", "style", "head", "title", "nav", "svg", "math"}


def _clean(text: str) -> str:
    text = unicodedata.normalize("NFC", text)
    text = text.replace("\u00a0", " ").replace("\u200b", "").replace("\u00ad", "")
    return re.sub(r"\s+", " ", text).strip()


class _BlockExtractor(HTMLParser):
    """Walks XHTML/HTML and emits one Block per block-level element."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self._buf: list[str] = []
        self._skip_depth = 0
        self._heading_depth = 0

    def _flush(self) -> None:
        text = _clean("".join(self._buf))
        self._buf = []
        if text:
            kind = "heading" if self._heading_depth else "paragraph"
            self.blocks.append(Block(kind, text))

    def handle_starttag(self, tag, attrs):
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "br":
            self._buf.append(" ")
        elif tag in _BLOCK_TAGS:
            self._flush()
            if tag in _HEADING_TAGS:
                self._heading_depth += 1

    def handle_startendtag(self, tag, attrs):
        # Self-closing tags such as <br/> or <hr/>; never push depth.
        if self._skip_depth:
            return
        if tag == "br":
            self._buf.append(" ")
        elif tag in _BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag):
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _BLOCK_TAGS:
            self._flush()
            if tag in _HEADING_TAGS:
                self._heading_depth = max(0, self._heading_depth - 1)

    def handle_data(self, data):
        if not self._skip_depth:
            self._buf.append(data)

    def close(self):
        super().close()
        self._flush()


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _extract_blocks(raw: bytes) -> list[Block]:
    parser = _BlockExtractor()
    parser.feed(_decode(raw))
    parser.close()
    return parser.blocks


# check if file is valid ebook
def _local(tag: str) -> str:
    """Strip the XML namespace from a tag name."""
    return tag.rsplit("}", 1)[-1]


def _find_opf_path(zf: zipfile.ZipFile) -> str:
    try:
        container = ET.fromstring(zf.read("META-INF/container.xml"))
    except KeyError as e:
        raise EpubError("Missing META-INF/container.xml; not a valid EPUB.") from e
    for el in container.iter():
        if _local(el.tag) == "rootfile" and el.get("full-path"):
            return el.get("full-path")
    raise EpubError("container.xml does not point to a package (OPF) file.")


def _check_not_drm(zf: zipfile.ZipFile) -> None:
    """Font obfuscation is fine; anything else in encryption.xml is DRM."""
    try:
        data = zf.read("META-INF/encryption.xml")
    except KeyError:
        return
    font_algos = {
        "http://www.idpf.org/2008/embedding",
        "http://ns.adobe.com/pdf/enc#RC",
    }
    for el in ET.fromstring(data).iter():
        if _local(el.tag) == "EncryptionMethod":
            if el.get("Algorithm") not in font_algos:
                raise EpubError("This EPUB is DRM-protected and cannot be read.")


def _metadata(opf: ET.Element, name: str) -> str | None:
    for el in opf.iter():
        if _local(el.tag) == name and el.text and el.text.strip():
            return _clean(el.text)
    return None


def _first_heading(blocks: list[Block]) -> str | None:
    for b in blocks:
        if b.kind == "heading":
            return b.text
    return None


#parser
def parse_epub(path: str) -> Book:
    """Parse an EPUB file into a Book. Raises EpubError on unreadable input."""
    try:
        zf = zipfile.ZipFile(path)
    except (zipfile.BadZipFile, FileNotFoundError, IsADirectoryError) as e:
        raise EpubError(f"Cannot open {path!r} as an EPUB: {e}") from e

    with zf:
        _check_not_drm(zf)
        opf_path = _find_opf_path(zf)
        opf_dir = posixpath.dirname(opf_path)
        try:
            opf = ET.fromstring(zf.read(opf_path))
        except (KeyError, ET.ParseError) as e:
            raise EpubError(f"Cannot read package file {opf_path!r}: {e}") from e

        # manifest: id -> (href, media_type, properties)
        manifest: dict[str, tuple[str, str, str]] = {}
        spine_ids: list[str] = []
        for el in opf.iter():
            tag = _local(el.tag)
            if tag == "item" and el.get("id") and el.get("href"):
                manifest[el.get("id")] = (
                    el.get("href"),
                    el.get("media-type", ""),
                    el.get("properties", ""),
                )
            elif tag == "itemref" and el.get("idref"):
                spine_ids.append(el.get("idref"))

        book = Book(
            title=_metadata(opf, "title"),
            author=_metadata(opf, "creator"),
            language=_metadata(opf, "language"),
        )

        names = set(zf.namelist())
        for idref in spine_ids:
            if idref not in manifest:
                continue
            href, media_type, props = manifest[idref]
            if "html" not in media_type or "nav" in props.split():
                continue  # skip non-text items and the EPUB3 navigation doc

            href_clean = unquote(urldefrag(href)[0])
            member = posixpath.normpath(posixpath.join(opf_dir, href_clean))
            if member not in names:
                continue

            blocks = _extract_blocks(zf.read(member))
            if not blocks:
                continue  # e.g. image-only cover pages

            book.chapters.append(
                Chapter(
                    index=len(book.chapters),
                    href=member,
                    title=_first_heading(blocks),
                    blocks=blocks,
                )
            )

    if not book.chapters:
        raise EpubError("No readable text found in this EPUB.")
    return book


def _main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in {"-h", "--help"}:
        print(__doc__)
        return 0
    try:
        book = parse_epub(argv[1])
    except EpubError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if "--json" in argv[2:]:
        print(json.dumps(book.to_dict(), ensure_ascii=False, indent=2))
        return 0

    print(f"Title:    {book.title}")
    print(f"Author:   {book.author}")
    print(f"Language: {book.language}")
    print(f"Chapters: {len(book.chapters)}")
    for ch in book.chapters[:10]:
        words = sum(len(p.split()) for p in ch.paragraphs)
        print(f"  [{ch.index}] {ch.title or '(untitled)'}  ({words} words)")
    if len(book.chapters) > 10:
        print(f"  ... and {len(book.chapters) - 10} more")
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))