"""
Dynamic Bible text fetcher with JSON file caching.

Fetches Bible text from external sources and caches locally as JSON files.
Supports multiple translations (NIV, NKJV, KJV, ESV) and Hebrew NT text.

Sources:
  - bible-api.com  → KJV (free, no API key, public domain)
  - BibleHub        → NIV, NKJV, ESV (web scraping with caching)
  - BibleHub        → Hebrew / Delitzsch NT (verse-by-verse scraping)
"""

import os
import json
import re
import html as html_module
import time
import logging
import requests

from bible_data import NT_BOOKS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "static", "data", "bible")

# How each translation is fetched
TRANSLATION_SOURCES = {
    "KJV":      "bible-api",
    "NIV":      "biblehub",
    "NKJV":     "biblehub",
    "ESV":      "biblehub",
    "NASB1995": "biblehub",
    "Hebrew":   "biblehub-hebrew",
}

# BibleHub URL translation codes
BIBLEHUB_CODES = {
    "NIV":      "niv",
    "NKJV":     "nkjv",
    "KJV":      "kjv",
    "ESV":      "esv",
    "NASB1995": "nasb",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------

def _cache_path(translation: str, book: str, chapter: int) -> str:
    """Return the filesystem path for a cached chapter."""
    info = NT_BOOKS.get(book)
    slug = info["slug"] if info else book.lower().replace(" ", "_")
    return os.path.join(CACHE_DIR, translation.lower(), slug, f"{chapter}.json")


def get_cached(translation: str, book: str, chapter: int):
    """Return cached verses dict {int: str} or None."""
    path = _cache_path(translation, book, chapter)
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return {int(k): v for k, v in data.items()}
    except Exception as exc:
        logger.warning("Cache read error %s: %s", path, exc)
        return None


def save_cache(translation: str, book: str, chapter: int, verses: dict):
    """Persist a verses dict to the JSON cache."""
    path = _cache_path(translation, book, chapter)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        data = {str(k): v for k, v in verses.items()}
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
    except Exception as exc:
        logger.warning("Cache write error %s: %s", path, exc)

# ---------------------------------------------------------------------------
# Source: bible-api.com  (KJV and other public-domain translations)
# ---------------------------------------------------------------------------

def fetch_from_bible_api(book: str, chapter: int, translation_code: str = "kjv"):
    """Fetch a full chapter from bible-api.com (free, no key required)."""
    try:
        book_url = book.replace(" ", "+")
        url = f"https://bible-api.com/{book_url}+{chapter}?translation={translation_code}"
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            logger.error("bible-api.com %s for %s %d", resp.status_code, book, chapter)
            return None
        data = resp.json()
        if "error" in data:
            logger.error("bible-api.com error: %s", data["error"])
            return None
        verses = {}
        for v in data.get("verses", []):
            num = v.get("verse")
            text = v.get("text", "").strip()
            if num and text:
                verses[int(num)] = text
        return verses or None
    except Exception as exc:
        logger.error("bible-api.com fetch error: %s", exc)
        return None

# ---------------------------------------------------------------------------
# Source: BibleHub  (NIV, NKJV, ESV – and KJV fallback)
# ---------------------------------------------------------------------------

def _clean_biblehub_text(raw: str) -> str:
    """Strip HTML tags, decode entities, normalise whitespace."""
    # 1. Remove footnote spans entirely (they contain single-letter markers like
    #    <span class="nivfootnote"><sup><a ...>b</a></sup></span>)
    text = re.sub(r'<span[^>]*class="[^"]*footnote[^"]*"[^>]*>.*?</span>', '', raw, flags=re.DOTALL | re.IGNORECASE)
    # 2. Remove any remaining <sup> tags and their contents (cross-refs, footnotes)
    text = re.sub(r'<sup[^>]*>.*?</sup>', '', text, flags=re.DOTALL)
    # 3. Remove all other HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    text = html_module.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    # 4. Remove any remaining standalone single-letter footnote markers
    #    (trailing: "...kingdom. a" → "...kingdom.")
    text = re.sub(r"\s+[a-z]\s*$", "", text).strip()
    #    (inline: "Messiah b the son" → "Messiah the son")
    text = re.sub(r"(?<=[\s,;:.!?])\s[a-z]\s(?=[A-Z])", " ", text)
    # 5. Fix doubled punctuation left behind (e.g. ",," → ",")
    text = re.sub(r"([,;:.])\1+", r"\1", text)
    # 6. Fix space before punctuation (e.g. "David , the" → "David, the")
    text = re.sub(r"\s+([,;:.!?])", r"\1", text)
    # 7. Final whitespace cleanup
    text = re.sub(r"\s+", " ", text).strip()
    return text


def fetch_from_biblehub(book: str, chapter: int, translation_code: str):
    """Fetch a full chapter from BibleHub for a given translation."""
    info = NT_BOOKS.get(book)
    if not info:
        return None
    slug = info["slug"]
    url = f"https://biblehub.com/{translation_code}/{slug}/{chapter}.htm"
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code != 200:
            logger.error("BibleHub %s for %s", resp.status_code, url)
            return None

        # BibleHub reports ISO-8859-1 but actual content is UTF-8
        resp.encoding = "utf-8"
        html = resp.text

        # Primary regex – matches the reftext/verse pattern used by BibleHub
        pattern = (
            r'<span\s+class="reftext">'     # opening reftext
            r'.*?<b>(\d+)</b>'               # verse number
            r'.*?</span>'                    # close reftext
            r'(.*?)'                         # verse body (group 2)
            r'(?=<span\s+class="reftext">'   # lookahead: next verse …
            r'|<div\s+id="botbox">'          # … or bottom box
            r'|<div\s+class="chapterbottom">'
            r'|<p\s+class="sectionhead">'
            r'|<hr\b'
            r'|</body>)'
        )
        matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
        verses = {}
        for m in matches:
            num = int(m[0])
            text = _clean_biblehub_text(m[1])
            if text:
                verses[num] = text
        return verses if verses else None
    except Exception as exc:
        logger.error("BibleHub fetch error (%s): %s", url, exc)
        return None

# ---------------------------------------------------------------------------
# Source: BibleHub Hebrew (Delitzsch NT – verse by verse)
# ---------------------------------------------------------------------------

def fetch_hebrew_chapter(book: str, chapter: int, max_verses: int = 200):
    """Fetch Hebrew (Delitzsch) NT text from BibleHub, one verse at a time."""
    info = NT_BOOKS.get(book)
    if not info:
        return None
    slug = info["slug"]
    verses = {}
    consecutive_misses = 0

    for verse_num in range(1, max_verses + 1):
        url = f"https://biblehub.com/text/{slug}/{chapter}-{verse_num}.htm"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                consecutive_misses += 1
                if consecutive_misses >= 3:
                    break
                continue

            # BibleHub reports ISO-8859-1 but content is actually UTF-8
            resp.encoding = "utf-8"

            # Extract Hebrew span
            match = re.search(r'<span class="heb">([^<]+)</span>', resp.text)
            if match:
                hebrew_text = match.group(1).strip()
                if hebrew_text:
                    verses[verse_num] = hebrew_text
                    consecutive_misses = 0
                else:
                    consecutive_misses += 1
            else:
                consecutive_misses += 1

            if consecutive_misses >= 3:
                break

            # Rate-limit to be polite
            time.sleep(0.3)

        except Exception as exc:
            logger.error("Hebrew verse error (%s %d:%d): %s", book, chapter, verse_num, exc)
            consecutive_misses += 1
            if consecutive_misses >= 3:
                break

    return verses if verses else None

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_verses(translation: str, book: str, chapter: int):
    """
    Return verses for a given translation / book / chapter.
    Checks local JSON cache first; fetches from the appropriate external
    source on cache miss and persists the result for next time.

    Returns: dict  {verse_number(int): verse_text(str)}  or  None
    """
    # Validate inputs
    if book not in NT_BOOKS:
        return None
    max_ch = NT_BOOKS[book]["chapters"]
    if chapter < 1 or chapter > max_ch:
        return None

    # 1. Check cache
    cached = get_cached(translation, book, chapter)
    if cached:
        return cached

    # 2. Fetch from external source
    source = TRANSLATION_SOURCES.get(translation)
    verses = None

    if source == "bible-api":
        verses = fetch_from_bible_api(book, chapter, translation.lower())
    elif source == "biblehub":
        code = BIBLEHUB_CODES.get(translation)
        if code:
            verses = fetch_from_biblehub(book, chapter, code)
    elif source == "biblehub-hebrew":
        verses = fetch_hebrew_chapter(book, chapter)

    # 3. Cache the result
    if verses:
        save_cache(translation, book, chapter, verses)

    return verses


def get_all_translations():
    """Return the list of supported translation codes."""
    return list(TRANSLATION_SOURCES.keys())


# ---------------------------------------------------------------------------
# Migration helper – export hardcoded translations.py data to JSON cache
# ---------------------------------------------------------------------------

def export_hardcoded_to_cache():
    """
    One-time helper: reads the hardcoded BIBLE_NIV / BIBLE_HEBREW dicts
    from translations.py and writes them into the JSON cache so that
    the dynamic system can serve them instantly without re-fetching.
    """
    try:
        from translations import BIBLE_NIV, BIBLE_HEBREW
    except ImportError:
        logger.info("No hardcoded translations to export.")
        return

    exported = 0
    for book in BIBLE_NIV:
        for chapter in BIBLE_NIV[book]:
            if not get_cached("NIV", book, chapter):
                save_cache("NIV", book, chapter, BIBLE_NIV[book][chapter])
                exported += 1

    for book in BIBLE_HEBREW:
        for chapter in BIBLE_HEBREW[book]:
            if not get_cached("Hebrew", book, chapter):
                save_cache("Hebrew", book, chapter, BIBLE_HEBREW[book][chapter])
                exported += 1

    if exported:
        logger.info("Exported %d chapters from hardcoded data to JSON cache.", exported)
