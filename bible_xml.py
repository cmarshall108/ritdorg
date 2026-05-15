"""
Local XML Bible source.

Reads Bible text from the XML files shipped under ``bible_data/`` and
serves verses to the rest of the app.  Translations are auto-discovered
from the directory; nothing has to be hard-coded.

Caching strategy
----------------
* Each translation file is parsed lazily on first access.
* Parsed translations are kept in an in-process LRU cache so subsequent
  lookups are constant-time dict access.
* The XML format is::

      <bible translation="...">
        <testament name="Old"|"New">
          <book number="1..66">
            <chapter number="N">
              <verse number="N">text</verse>
              ...

  Books are numbered 1..66 in canonical Protestant order (Genesis=1,
  Malachi=39, Matthew=40, Revelation=66) which matches the insertion
  order of :data:`bible_data.ALL_BOOKS`.
"""

from __future__ import annotations

import logging
import os
import re
from functools import lru_cache
from xml.etree import ElementTree as ET

from bible_data import ALL_BOOKS

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XML_DIR = os.path.join(BASE_DIR, "bible_data")

# Canonical 1-based book number for each book name.
BOOK_NUMBER: dict[str, int] = {
    name: idx + 1 for idx, name in enumerate(ALL_BOOKS.keys())
}

# Friendly translation names that the existing UI / hard-coded data
# already use.  Map them to the matching XML basename so old links keep
# working.
LEGACY_ALIASES: dict[str, str] = {
    "KJV": "EnglishKJ",
    "NIV": "EnglishNIV",
    "ESV": "EnglishESV",
    "NKJV": "EnglishNKJ",
    "NASB1995": "EnglishNASU",   # NASB Updated edition
    "NASB": "EnglishNASB",
    "Hungarian": "HungarianKaroli",
    "Hungarian-Revised": "HungarianRUF",
    "Hebrew": "Hebrew",
}

_FILENAME_SUFFIX = re.compile(r"Bible\.xml$", re.IGNORECASE)


def _filename_to_name(filename: str) -> str:
    """Return the friendly translation name for an XML filename."""
    return _FILENAME_SUFFIX.sub("", filename)


@lru_cache(maxsize=1)
def _name_to_path() -> dict[str, str]:
    """Map every discovered translation name to its absolute XML path."""
    out: dict[str, str] = {}
    if not os.path.isdir(XML_DIR):
        return out
    for fn in os.listdir(XML_DIR):
        if fn.lower().endswith("bible.xml"):
            out[_filename_to_name(fn)] = os.path.join(XML_DIR, fn)
    return out


@lru_cache(maxsize=1)
def list_translations() -> list[str]:
    """Sorted list of every translation available as an XML file."""
    return sorted(_name_to_path().keys())


def resolve_translation(name: str | None) -> str | None:
    """Resolve a user-supplied translation name to a known XML basename."""
    if not name:
        return None
    files = _name_to_path()
    if name in files:
        return name
    alias = LEGACY_ALIASES.get(name)
    if alias and alias in files:
        return alias
    lower = name.lower()
    for f in files:
        if f.lower() == lower:
            return f
    return None


@lru_cache(maxsize=8)
def _load(translation: str):
    """Parse one translation's XML into nested dicts.

    Returns ``{book_num: {chapter_num: {verse_num: text}}}`` or ``None``.
    """
    path = _name_to_path().get(translation)
    if not path or not os.path.exists(path):
        return None
    try:
        tree = ET.parse(path)
    except ET.ParseError as exc:
        logger.warning("Bible XML parse error %s: %s", path, exc)
        return None

    result: dict[int, dict[int, dict[int, str]]] = {}
    for book_el in tree.getroot().iter("book"):
        try:
            bn = int(book_el.get("number", "0"))
        except (TypeError, ValueError):
            continue
        chapters: dict[int, dict[int, str]] = {}
        for ch_el in book_el.findall("chapter"):
            try:
                cn = int(ch_el.get("number", "0"))
            except (TypeError, ValueError):
                continue
            verses: dict[int, str] = {}
            for v_el in ch_el.findall("verse"):
                try:
                    vn = int(v_el.get("number", "0"))
                except (TypeError, ValueError):
                    continue
                text = (v_el.text or "").strip()
                if text:
                    verses[vn] = text
            if verses:
                chapters[cn] = verses
        if chapters:
            result[bn] = chapters
    return result


def get_verses(translation: str, book: str, chapter: int) -> dict[int, str] | None:
    """Return ``{verse_num: text}`` for the requested chapter, or ``None``."""
    book_num = BOOK_NUMBER.get(book)
    if not book_num:
        return None
    resolved = resolve_translation(translation)
    if not resolved:
        return None
    data = _load(resolved)
    if not data:
        return None
    chapter_dict = data.get(book_num, {}).get(chapter)
    if not chapter_dict:
        return None
    # Return a shallow copy so callers can mutate freely.
    return dict(chapter_dict)


def has_translation(translation: str) -> bool:
    """Return True if the given name resolves to an XML file on disk."""
    return resolve_translation(translation) is not None
