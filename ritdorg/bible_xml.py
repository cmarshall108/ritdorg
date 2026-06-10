"""
Local XML Bible source.

Reads Bible text from the XML files shipped under ``bible_data/`` and
serves verses to the rest of the app.  Translations are auto-discovered
from the directory; nothing has to be hard-coded.

Caching strategy
----------------
* Each translation file is parsed lazily on first access.
* Parsed translations are persisted to a pickle file under
  ``data/bible-cache/`` so subsequent process starts skip the (slow)
  XML reparse — the pickle round-trip is ~10x faster than ET.parse.
* Hot translations are also kept in an in-process dict so repeated
  lookups within a single process are constant-time.
* A small thread pool pre-warms the most common English + Hebrew
  translations on import so the first request doesn't pay the parse
  cost on the request thread.
* Concurrent calls for the same uncached translation are deduped via a
  per-translation lock (single-flight); multiple distinct translations
  load in parallel.
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
import pickle
import re
import threading
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from xml.etree import ElementTree as ET

from .bible_data import ALL_BOOKS

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XML_DIR = os.path.join(BASE_DIR, "bible_data")
CACHE_DIR = os.path.join(BASE_DIR, "data", "bible-cache")
# Bump if the parsed-data shape changes so old pickles are ignored.
CACHE_VERSION = 1
# How many parsed translations to keep resident in memory at once.
# Each is a few MB of dicts; 64 fits comfortably and covers the most
# common workloads (sync view = 2, parallel view = 2, search etc.).
_MEM_CACHE_MAX = 64
# Translations to pre-load in the background so the very first request
# never has to wait for an XML parse / pickle read.
_PREWARM = (
    "EnglishNIV", "EnglishKJ", "EnglishESV", "EnglishNKJ",
    "EnglishNASB", "EnglishNASU", "Hebrew",
)

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


# ---------------------------------------------------------------------------
# Cache plumbing
# ---------------------------------------------------------------------------

# In-memory parsed cache (LRU, thread-safe via _mem_lock).
_mem_cache: "OrderedDict[str, dict]" = OrderedDict()
_mem_lock = threading.Lock()
# Per-translation single-flight locks so two threads asking for the same
# uncached translation only do the work once.
_load_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()


def _get_load_lock(translation: str) -> threading.Lock:
    with _locks_lock:
        lk = _load_locks.get(translation)
        if lk is None:
            lk = threading.Lock()
            _load_locks[translation] = lk
        return lk


def _store_in_mem(translation: str, parsed: dict) -> None:
    with _mem_lock:
        if translation in _mem_cache:
            _mem_cache.move_to_end(translation)
        _mem_cache[translation] = parsed
        while len(_mem_cache) > _MEM_CACHE_MAX:
            _mem_cache.popitem(last=False)


def _get_from_mem(translation: str):
    with _mem_lock:
        parsed = _mem_cache.get(translation)
        if parsed is not None:
            _mem_cache.move_to_end(translation)
        return parsed


def _cache_path(translation: str) -> str:
    return os.path.join(CACHE_DIR, f"{translation}.v{CACHE_VERSION}.pkl")


def _parse_xml(path: str):
    """Parse one Bible XML file into nested dicts. Returns ``None`` on error."""
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


def _load(translation: str):
    """Return parsed dict for *translation* (mem → pickle → XML), or ``None``."""
    parsed = _get_from_mem(translation)
    if parsed is not None:
        return parsed

    # Dedupe concurrent loads of the same translation.
    with _get_load_lock(translation):
        parsed = _get_from_mem(translation)
        if parsed is not None:
            return parsed

        path = _name_to_path().get(translation)
        if not path or not os.path.exists(path):
            return None

        cache_path = _cache_path(translation)
        # Use the pickle cache if it's at least as new as the source XML.
        try:
            xml_mtime = os.path.getmtime(path)
            cache_mtime = (
                os.path.getmtime(cache_path) if os.path.exists(cache_path) else 0.0
            )
            if cache_mtime >= xml_mtime:
                with open(cache_path, "rb") as fh:
                    parsed = pickle.load(fh)
                _store_in_mem(translation, parsed)
                return parsed
        except (OSError, pickle.PickleError, EOFError, ValueError) as exc:
            logger.warning(
                "Bible cache read failed %s: %s; reparsing XML", cache_path, exc
            )

        parsed = _parse_xml(path)
        if parsed is None:
            return None

        # Persist for the next process start (best-effort).
        try:
            os.makedirs(CACHE_DIR, exist_ok=True)
            tmp = cache_path + ".tmp"
            with open(tmp, "wb") as fh:
                pickle.dump(parsed, fh, protocol=pickle.HIGHEST_PROTOCOL)
            os.replace(tmp, cache_path)
        except OSError as exc:
            logger.warning("Bible cache write failed %s: %s", cache_path, exc)

        _store_in_mem(translation, parsed)
        return parsed


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


# ---------------------------------------------------------------------------
# Background pre-warm
# ---------------------------------------------------------------------------

_prewarm_started = False
_prewarm_lock = threading.Lock()


def _prewarm_worker(targets: list[str]) -> None:
    # Use a small pool so we parallelize parsing/pickle reads across cores
    # without thrashing disk on cold start.
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="bible-prewarm") as ex:
        for _ in ex.map(_load, targets):
            pass


def start_prewarm(extra: list[str] | None = None) -> None:
    """Kick off a background thread that pre-loads common translations.

    Safe to call more than once; only the first call schedules work.
    """
    global _prewarm_started
    with _prewarm_lock:
        if _prewarm_started:
            return
        _prewarm_started = True

    available = _name_to_path()
    targets = [t for t in _PREWARM if t in available]
    if extra:
        for t in extra:
            r = resolve_translation(t)
            if r and r not in targets:
                targets.append(r)
    if not targets:
        return

    t = threading.Thread(
        target=_prewarm_worker,
        args=(targets,),
        name="bible-prewarm-launcher",
        daemon=True,
    )
    t.start()


# Auto-start pre-warm on import — cheap (returns immediately) and means
# the first user request doesn't pay the cold parse cost.
start_prewarm()
