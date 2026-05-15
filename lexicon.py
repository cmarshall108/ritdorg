"""
Strong's Hebrew & Greek lexicon.

Loads the public-domain "A Concise Dictionary of the Words in the
Hebrew Bible / Dictionary of Greek Words" (Strong's, as published by
the OpenScriptures project) and serves entries by id, lemma, or
transliteration.

Data source
-----------
* Hebrew: https://github.com/openscriptures/strongs (master)
* Greek:  same repo

The upstream files are JavaScript that assigns to a global, e.g.
``var strongsHebrewDictionary = { "H1": {...}, ... };``
After stripping the ``var X = `` prefix and trailing ``;`` the body is
valid JSON, which we cache as ``data/strongs/<lang>.json`` for fast
subsequent loads.

Caching
-------
* First request triggers a single-flight HTTPS download (~3 MB total
  for both languages combined).
* Parsed dictionaries are kept in process memory.
* A background thread can be kicked with :func:`start_prewarm` to load
  both lexicons at startup so first user requests are instant.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(BASE_DIR, "data", "strongs")

SOURCES = {
    "hebrew": "https://raw.githubusercontent.com/openscriptures/strongs/master/hebrew/strongs-hebrew-dictionary.js",
    "greek":  "https://raw.githubusercontent.com/openscriptures/strongs/master/greek/strongs-greek-dictionary.js",
}

# Strong's id prefix per language.
_PREFIX = {"hebrew": "H", "greek": "G"}

_VAR_PREFIX_RE = re.compile(r"^\s*(?:/\*.*?\*/\s*)*var\s+\w+\s*=\s*", re.DOTALL)

_mem: dict[str, dict] = {}
_mem_lock = threading.Lock()
_load_locks: dict[str, threading.Lock] = {}
_locks_lock = threading.Lock()
# Searchable indexes (built lazily): lower(lemma|translit|xlit) -> [strongs_id]
_index: dict[str, dict[str, list[str]]] = {}


def _get_load_lock(lang: str) -> threading.Lock:
    with _locks_lock:
        lk = _load_locks.get(lang)
        if lk is None:
            lk = threading.Lock()
            _load_locks[lang] = lk
        return lk


def _cache_path(lang: str) -> str:
    return os.path.join(CACHE_DIR, f"strongs-{lang}.json")


def _download(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "ritdorg-lexicon/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def _js_to_json(src: str) -> str:
    """Extract the dictionary literal from the upstream JS file.

    The file looks like::

        /* header comment */
        var strongsHebrewDictionary = { "H1": {...}, ... };
        module.exports = strongsHebrewDictionary;

    We strip the leading ``var X = `` and then walk braces to find the
    matching ``}`` so we ignore any trailing CommonJS export.
    """
    body = _VAR_PREFIX_RE.sub("", src, count=1).lstrip()
    if not body or body[0] != "{":
        # Fall back to "find the first { ourselves".
        i = body.find("{")
        if i < 0:
            return ""
        body = body[i:]
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i, ch in enumerate(body):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return body  # let json.loads raise a clear error
    return body[:end]


def _normalize_entries(raw: dict) -> dict[str, dict]:
    """Lower-case keys (kjv vs KJV variants) and ensure required fields exist."""
    out: dict[str, dict] = {}
    for sid, entry in raw.items():
        if not isinstance(entry, dict):
            continue
        out[sid] = {
            "id": sid,
            "lemma": entry.get("lemma", ""),
            "translit": entry.get("translit") or entry.get("xlit") or "",
            "pron": entry.get("pron", ""),
            "derivation": entry.get("derivation", ""),
            "strongs_def": (entry.get("strongs_def") or "").strip(),
            "kjv_def": (entry.get("kjv_def") or "").strip(),
        }
    return out


def _build_index(entries: dict[str, dict]) -> dict[str, list[str]]:
    idx: dict[str, list[str]] = {}
    for sid, e in entries.items():
        for key in (e.get("lemma"), e.get("translit"), e.get("pron")):
            if not key:
                continue
            k = key.strip().lower()
            if not k:
                continue
            idx.setdefault(k, []).append(sid)
    return idx


def _load(lang: str) -> dict[str, dict] | None:
    lang = lang.lower()
    if lang not in SOURCES:
        return None
    with _mem_lock:
        cached = _mem.get(lang)
    if cached is not None:
        return cached

    with _get_load_lock(lang):
        with _mem_lock:
            cached = _mem.get(lang)
        if cached is not None:
            return cached

        cache_path = _cache_path(lang)
        raw_json: str | None = None
        # Prefer the local cache; fall back to a fresh download.
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as fh:
                    raw_json = fh.read()
            except OSError as exc:
                logger.warning("lexicon cache read failed %s: %s", cache_path, exc)
        if raw_json is None:
            try:
                src = _download(SOURCES[lang])
                raw_json = _js_to_json(src)
                # Persist for next time (best-effort).
                try:
                    os.makedirs(CACHE_DIR, exist_ok=True)
                    tmp = cache_path + ".tmp"
                    with open(tmp, "w", encoding="utf-8") as fh:
                        fh.write(raw_json)
                    os.replace(tmp, cache_path)
                except OSError as exc:
                    logger.warning("lexicon cache write failed %s: %s", cache_path, exc)
            except Exception as exc:
                logger.error("lexicon download failed for %s: %s", lang, exc)
                return None

        try:
            raw = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            logger.error("lexicon parse failed for %s: %s", lang, exc)
            return None

        entries = _normalize_entries(raw)
        with _mem_lock:
            _mem[lang] = entries
            _index[lang] = _build_index(entries)
        return entries


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_entry(lang: str, strongs_id: str) -> dict | None:
    """Return one normalized lexicon entry by Strong's id (e.g. ``H7225``)."""
    if not strongs_id:
        return None
    sid = strongs_id.strip().upper()
    # Accept "7225" → "H7225" if lang specified.
    pref = _PREFIX.get((lang or "").lower())
    if pref and sid.isdigit():
        sid = f"{pref}{int(sid)}"
    if not sid or sid[0] not in ("H", "G"):
        return None
    actual_lang = "hebrew" if sid[0] == "H" else "greek"
    if lang and lang.lower() != actual_lang:
        return None
    entries = _load(actual_lang)
    if not entries:
        return None
    # Try direct match first.
    e = entries.get(sid)
    if e:
        return e
    # OpenScriptures Hebrew sometimes pads to 4 digits (H0001 vs H1).
    head, num = sid[0], sid[1:].lstrip("0") or "0"
    return entries.get(f"{head}{num}") or entries.get(f"{head}{int(num):04d}")


def search(lang: str, query: str, *, limit: int = 50) -> list[dict]:
    """Search the lexicon by lemma, transliteration, pronunciation, or
    free-text gloss. Returns a list of normalized entries (best matches
    first), capped at *limit*.
    """
    lang = (lang or "").lower()
    if lang not in SOURCES:
        return []
    entries = _load(lang)
    if not entries:
        return []
    q = (query or "").strip()
    if not q:
        return []

    # Strong's id shortcut.
    qu = q.upper()
    if qu.startswith(("H", "G")) and qu[1:].lstrip("0").isdigit():
        e = get_entry(lang, qu)
        return [e] if e else []
    if q.isdigit():
        e = get_entry(lang, q)
        return [e] if e else []

    idx = _index.get(lang) or {}
    ql = q.lower()

    # 1) Exact key match (lemma/translit/pron).
    exact_ids = idx.get(ql, [])
    seen: set[str] = set()
    results: list[dict] = []
    for sid in exact_ids:
        if sid in seen:
            continue
        seen.add(sid)
        results.append(entries[sid])
        if len(results) >= limit:
            return results

    # 2) Prefix match across the index (cheap on ~10k keys).
    if len(results) < limit:
        for key, ids in idx.items():
            if key.startswith(ql) and key != ql:
                for sid in ids:
                    if sid in seen:
                        continue
                    seen.add(sid)
                    results.append(entries[sid])
                    if len(results) >= limit:
                        return results

    # 3) Substring match in lemma / translit / glosses.
    if len(results) < limit:
        for sid, e in entries.items():
            if sid in seen:
                continue
            haystack = " ".join((
                e.get("lemma", ""),
                e.get("translit", ""),
                e.get("strongs_def", ""),
                e.get("kjv_def", ""),
            )).lower()
            if ql in haystack:
                seen.add(sid)
                results.append(e)
                if len(results) >= limit:
                    return results
    return results


def is_loaded(lang: str) -> bool:
    with _mem_lock:
        return (lang or "").lower() in _mem


# ---------------------------------------------------------------------------
# Background prewarm
# ---------------------------------------------------------------------------

_prewarm_started = False
_prewarm_lock = threading.Lock()


def start_prewarm() -> None:
    """Pre-load both lexicons in a background thread."""
    global _prewarm_started
    with _prewarm_lock:
        if _prewarm_started:
            return
        _prewarm_started = True

    def worker():
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="lexicon-prewarm") as ex:
            for _ in ex.map(_load, ("hebrew", "greek")):
                pass

    threading.Thread(target=worker, name="lexicon-prewarm-launcher", daemon=True).start()


# Auto-prewarm on import. The download is one-time (cached to disk) so
# the cost is paid once per deployment, not per request.
start_prewarm()
