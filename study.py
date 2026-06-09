"""Pastor / leader / researcher study-tools blueprint.

Adds a single Flask Blueprint (`study_bp`) plus helper functions backing
24 new features, all sharing the existing ``data/auth.db`` SQLite file
and the existing per-visitor identity model from ``auth.py`` (logged-in
``user_id`` or anonymous ``device_key`` cookie).

All endpoints live under the URL prefix the blueprint is registered with
(typically ``/api``). Mobile-friendly: every response is small JSON or
streaming bytes; the heaviest searches are index-backed and bounded by
``limit``.

New SQLite tables (created on import via :func:`init_study_db`):

    tags                — (id, owner, name, color, created_at)
    tag_links           — (tag_id, book, chapter, verse, created_at)
    outlines            — (id, owner, title, theme, body_md, updated_at)
    outline_verses      — (outline_id, ord, book, chapter, verse, label)
    playlists           — (id, owner, title, description, created_at)
    playlist_items      — (playlist_id, ord, book, chapter, verse_start, verse_end, note)
    plan_progress       — (owner, plan_slug, day, completed_at)
    notebooks           — (id, owner, title, description, share_token, created_at)
    notebook_members    — (notebook_id, user_id, role, joined_at)
    notebook_entries    — (id, notebook_id, owner, book, chapter, verse, body_md, created_at)
    settings            — (owner, key, value)            -- for permalink prefs / dyslexia / etc.

The `owner` column is shorthand for the same (user_id|device_key) pair the
core tables use; helpers below handle the join uniformly.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import time
import zipfile
import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterable, Optional

from flask import (
    Blueprint, Response, abort, current_app, jsonify, request, send_file, url_for,
)

import auth
from bible_data import ALL_BOOKS

logger = logging.getLogger(__name__)


# --- DB plumbing -----------------------------------------------------------

@contextmanager
def _db():
    os.makedirs(os.path.dirname(auth.AUTH_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(auth.AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _owner_clause():
    """(sql, params) selecting rows owned by the current visitor.

    Mirrors auth._owner_filter but lives here so we don't poke at private
    helpers from another module.
    """
    from flask import g
    user = g.get("current_user") or {}
    if user.get("id"):
        return ("user_id = ?", (user["id"],))
    key = g.get("device_key")
    if key:
        return ("device_key = ?", (key,))
    return ("1 = 0", ())


def _owner_columns():
    from flask import g
    user = g.get("current_user") or {}
    if user.get("id"):
        return (user["id"], None)
    return (None, g.get("device_key"))


def _has_owner() -> bool:
    from flask import g
    user = g.get("current_user") or {}
    return bool(user.get("id") or g.get("device_key"))


def init_study_db() -> None:
    """Create study tables. Idempotent."""
    with _db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tags (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                name        TEXT NOT NULL,
                color       TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS tags_owner_idx ON tags(user_id, device_key);

            CREATE TABLE IF NOT EXISTS tag_links (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_id      INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
                book        TEXT NOT NULL,
                chapter     INTEGER NOT NULL,
                verse       INTEGER NOT NULL,
                created_at  TEXT NOT NULL,
                UNIQUE(tag_id, book, chapter, verse)
            );
            CREATE INDEX IF NOT EXISTS tag_links_tag_idx ON tag_links(tag_id);
            CREATE INDEX IF NOT EXISTS tag_links_loc_idx ON tag_links(book, chapter, verse);

            CREATE TABLE IF NOT EXISTS outlines (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                title       TEXT NOT NULL,
                theme       TEXT,
                body_md     TEXT,
                updated_at  TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS outlines_owner_idx ON outlines(user_id, device_key);

            CREATE TABLE IF NOT EXISTS outline_verses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                outline_id  INTEGER NOT NULL REFERENCES outlines(id) ON DELETE CASCADE,
                ord         INTEGER NOT NULL,
                book        TEXT NOT NULL,
                chapter     INTEGER NOT NULL,
                verse       INTEGER NOT NULL,
                label       TEXT
            );
            CREATE INDEX IF NOT EXISTS outline_verses_outline_idx
                ON outline_verses(outline_id, ord);

            CREATE TABLE IF NOT EXISTS playlists (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                title       TEXT NOT NULL,
                description TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS playlists_owner_idx ON playlists(user_id, device_key);

            CREATE TABLE IF NOT EXISTS playlist_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                playlist_id INTEGER NOT NULL REFERENCES playlists(id) ON DELETE CASCADE,
                ord         INTEGER NOT NULL,
                book        TEXT NOT NULL,
                chapter     INTEGER NOT NULL,
                verse_start INTEGER,
                verse_end   INTEGER,
                note        TEXT
            );
            CREATE INDEX IF NOT EXISTS playlist_items_pl_idx
                ON playlist_items(playlist_id, ord);

            CREATE TABLE IF NOT EXISTS plan_progress (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                plan_slug   TEXT NOT NULL,
                day         INTEGER NOT NULL,
                completed_at TEXT NOT NULL,
                UNIQUE(user_id, plan_slug, day),
                UNIQUE(device_key, plan_slug, day)
            );
            CREATE INDEX IF NOT EXISTS plan_progress_owner_idx
                ON plan_progress(user_id, device_key, plan_slug);

            CREATE TABLE IF NOT EXISTS notebooks (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                title        TEXT NOT NULL,
                description  TEXT,
                share_token  TEXT UNIQUE,
                created_at   TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS notebook_members (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                notebook_id INTEGER NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                role        TEXT NOT NULL DEFAULT 'member',
                joined_at   TEXT NOT NULL,
                UNIQUE(notebook_id, user_id)
            );

            CREATE TABLE IF NOT EXISTS notebook_entries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                notebook_id INTEGER NOT NULL REFERENCES notebooks(id) ON DELETE CASCADE,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                book        TEXT,
                chapter     INTEGER,
                verse       INTEGER,
                body_md     TEXT NOT NULL,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS notebook_entries_nb_idx
                ON notebook_entries(notebook_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS settings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                key         TEXT NOT NULL,
                value       TEXT,
                UNIQUE(user_id, key),
                UNIQUE(device_key, key)
            );
            """
        )


# --- Curated reference data ------------------------------------------------

# Treasury of Scripture Knowledge — the public-domain TSK is huge (>500k
# refs). Bundling a hand-picked subset keeps the repo small while still
# being immediately useful in popular passages. The full set can be
# loaded from `data/cross_references.json` if present.
_TSK_SEED = {
    # John 3:16
    "John 3:16": [
        "1 John 4:9", "Romans 5:8", "John 1:14", "1 John 4:10",
        "Romans 8:32", "John 3:36", "Romans 6:23",
    ],
    "Genesis 1:1": [
        "John 1:1", "Hebrews 11:3", "Psalm 33:6", "Colossians 1:16",
        "Revelation 4:11", "Isaiah 42:5",
    ],
    "Romans 8:28": [
        "Genesis 50:20", "Ephesians 1:11", "James 1:2-4",
        "2 Corinthians 4:17",
    ],
    "Matthew 28:19": [
        "Mark 16:15", "Acts 1:8", "Luke 24:47", "Isaiah 52:10",
    ],
    "Psalms 23:1": [
        "John 10:11", "Isaiah 40:11", "Ezekiel 34:11-12", "Psalm 80:1",
    ],
    "Philippians 4:13": [
        "2 Corinthians 12:9", "Ephesians 3:16", "Colossians 1:11",
    ],
    "1 Corinthians 13:4": [
        "1 Corinthians 13:5-7", "Galatians 5:22", "Colossians 3:12-14",
    ],
}


def _load_cross_refs() -> dict:
    """Merge the seed with a bundled JSON file (if present)."""
    path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data", "cross_references.json",
    )
    out = dict(_TSK_SEED)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                more = json.load(f)
            if isinstance(more, dict):
                for k, v in more.items():
                    if isinstance(v, list):
                        out[k] = v
        except Exception:
            pass  # optional cross-ref pack not present or unreadable; degrade gracefully
    return out


_CROSS_REFS = None


def cross_refs() -> dict:
    global _CROSS_REFS
    if _CROSS_REFS is None:
        _CROSS_REFS = _load_cross_refs()
    return _CROSS_REFS


# Reading plans bundled with the app. Day -> list of "Book c[:v-v]" refs.
# Kept small + composable; the engine handles arbitrary plans.
def _gen_chronological_plan() -> list[list[str]]:
    """Whole-Bible read in 365 days, ~3 chapters/day in canonical order."""
    seq: list[str] = []
    for book, info in ALL_BOOKS.items():
        for ch in range(1, info["chapters"] + 1):
            seq.append(f"{book} {ch}")
    days = 365
    chunk = max(1, len(seq) // days)
    plan: list[list[str]] = []
    i = 0
    while i < len(seq) and len(plan) < days:
        plan.append(seq[i:i + chunk])
        i += chunk
    # Append any remainder to the last day.
    if i < len(seq) and plan:
        plan[-1].extend(seq[i:])
    return plan


_PLANS = {
    "ot-90": {
        "title": "Old Testament in 90 days",
        "summary": "Walk straight through the OT at ~10 chapters/day.",
        "days": None,  # generated lazily
    },
    "nt-90": {
        "title": "New Testament in 90 days",
        "summary": "All 27 NT books at ~3 chapters/day.",
        "days": None,
    },
    "psalms-30": {
        "title": "Psalms in 30 days",
        "summary": "Five Psalms a day for one month.",
        "days": None,
    },
    "gospels-40": {
        "title": "Gospels in 40 days",
        "summary": "Matthew → John, ~2 chapters/day.",
        "days": None,
    },
    "bible-365": {
        "title": "Whole Bible in a year",
        "summary": "Canonical order, ~3 chapters/day.",
        "days": None,
    },
}


def _build_plan_days(slug: str) -> list[list[str]]:
    if slug == "bible-365":
        return _gen_chronological_plan()
    if slug == "ot-90":
        seq = [f"{b} {c}" for b, info in ALL_BOOKS.items() if b in _ot_books()
               for c in range(1, info["chapters"] + 1)]
        return _split_evenly(seq, 90)
    if slug == "nt-90":
        seq = [f"{b} {c}" for b, info in ALL_BOOKS.items() if b not in _ot_books()
               for c in range(1, info["chapters"] + 1)]
        return _split_evenly(seq, 90)
    if slug == "psalms-30":
        return _split_evenly([f"Psalms {c}" for c in range(1, 151)], 30)
    if slug == "gospels-40":
        seq = [f"{b} {c}" for b in ("Matthew", "Mark", "Luke", "John")
               for c in range(1, ALL_BOOKS[b]["chapters"] + 1)]
        return _split_evenly(seq, 40)
    return []


def _ot_books() -> set[str]:
    from bible_data import OT_BOOKS
    return set(OT_BOOKS.keys())


def _split_evenly(items: list, days: int) -> list[list]:
    if not items:
        return []
    per = max(1, -(-len(items) // days))  # ceil
    return [items[i:i + per] for i in range(0, len(items), per)][:days]


def get_plan(slug: str) -> Optional[dict]:
    meta = _PLANS.get(slug)
    if not meta:
        return None
    days = _build_plan_days(slug)
    return {"slug": slug, "title": meta["title"], "summary": meta["summary"], "days": days}


# ---------------------------------------------------------------------------
# Blueprint
# ---------------------------------------------------------------------------

study_bp = Blueprint("study", __name__)


# --- Cross-translation concordance (#1) -----------------------------------

@study_bp.route("/words/concordance")
def words_concordance():
    """Cross-translation occurrence breakdown.

    Query: ?word=<text>&translations=NIV,KJV,Hungarian (default: ALL)

    Returns:
      { word, breakdown: { TRANSLATION: { count, verses } } }
    """
    from app import (
        TRANSLATION_DIR_SLUGS, TRANSLATION_LANG,
        _normalize_word_for_lang, _load_translation_corpus,
    )
    raw = (request.args.get("word") or "").strip()
    if not raw:
        return jsonify({"error": "word required"}), 400
    requested = (request.args.get("translations") or "ALL").strip()
    if requested.upper() == "ALL":
        names = sorted(TRANSLATION_DIR_SLUGS.keys())
    else:
        names = [t.strip() for t in requested.split(",") if t.strip() in TRANSLATION_DIR_SLUGS]
        if not names:
            return jsonify({"error": "no valid translations"}), 400

    out: dict = {}
    for tr in names:
        lang = TRANSLATION_LANG.get(tr, "en")
        target = _normalize_word_for_lang(raw, lang)
        if not target:
            out[tr] = {"count": 0, "verses": 0, "lang": lang}
            continue
        corpus = _load_translation_corpus(tr)
        hits = 0
        verses = 0
        for (_book, _ch, _v, _t, norm) in corpus:
            tokens = norm.split() if lang == "he" else norm.split(" ")
            n = sum(1 for t in tokens if t == target)
            if n:
                hits += n
                verses += 1
        out[tr] = {"count": hits, "verses": verses, "lang": lang}
    return jsonify({"word": raw, "breakdown": out})


# --- Hebrew lemma → cross-translation bridge (#2) -------------------------

@study_bp.route("/hebrew/lemma-bridge")
def hebrew_lemma_bridge():
    """Given a Hebrew word, return the dictionary gloss plus suggested
    English equivalents to search for in other translations.

    The curated dictionary stores short English glosses; we tokenize the
    gloss and surface every meaningful word as a candidate. The client
    can then call /api/words/concordance for any chosen word.
    """
    from app import _load_hebrew_dict, _strip_hebrew_marks
    word = (request.args.get("word") or "").strip()
    if not word:
        return jsonify({"error": "word required"}), 400
    direct, norm_map = _load_hebrew_dict()
    gloss = direct.get(word)
    matched = word
    if gloss is None:
        n = _strip_hebrew_marks(word)
        if n in norm_map:
            matched, gloss = norm_map[n]
    if gloss is None:
        return jsonify({"word": word, "gloss": None, "candidates": []}), 404
    # Pull out content words (drop articles, prepositions, etc.).
    STOP = {"the", "a", "an", "of", "in", "on", "to", "and", "or", "for",
            "with", "from", "by", "be", "is", "are", "was", "were", "as",
            "at", "it", "he", "she", "they"}
    candidates: list[str] = []
    for tok in re.findall(r"[A-Za-z']+", gloss.lower()):
        if tok in STOP or len(tok) < 3:
            continue
        if tok not in candidates:
            candidates.append(tok)
    return jsonify({
        "word": word, "matched": matched, "gloss": gloss,
        "candidates": candidates[:8],
    })


# --- Phrase / multi-word search (#3) --------------------------------------

@study_bp.route("/words/search")
def words_search():
    """Multi-token search with optional book/translation filters.

    Query:
        q            — required, may include "double quoted phrase",
                       AND-joined bare tokens, and book:NAME filters.
        translation  — display name (default NIV).
        limit        — max results (default 50).
    Returns:
        { count, truncated, results: [{book, chapter, verse, text, snippet}] }
    """
    from app import (
        _load_translation_corpus, _tokenize_for_lang, TRANSLATION_DIR_SLUGS,
        TRANSLATION_LANG,
    )
    qraw = (request.args.get("q") or "").strip()
    if not qraw:
        return jsonify({"error": "q required"}), 400
    translation = (request.args.get("translation") or "NIV").strip()
    if translation not in TRANSLATION_DIR_SLUGS:
        return jsonify({"error": "unknown translation"}), 400
    try:
        limit = max(1, min(int(request.args.get("limit") or 50), 500))
    except ValueError:
        limit = 50

    lang = TRANSLATION_LANG.get(translation, "en")

    # Parse: extract book filter, quoted phrases, bare tokens.
    book_filter: Optional[str] = None
    phrases: list[str] = []
    tokens: list[str] = []
    for m in re.finditer(r'"([^"]+)"|book:([^\s]+)|(\S+)', qraw):
        ph, bk, bare = m.group(1), m.group(2), m.group(3)
        if bk:
            # Match a known book either by exact name or slug.
            bn = bk.replace("_", " ").strip()
            for canonical in ALL_BOOKS:
                if canonical.lower() == bn.lower():
                    book_filter = canonical
                    break
        elif ph:
            phrases.append(ph)
        elif bare:
            tokens.append(bare)

    norm_phrases = [" ".join(_tokenize_for_lang(p, lang)) for p in phrases if p.strip()]
    norm_phrases = [p for p in norm_phrases if p]
    norm_tokens = [_tokenize_for_lang(t, lang) for t in tokens]
    norm_tokens = [t for sub in norm_tokens for t in sub]

    if not norm_phrases and not norm_tokens:
        return jsonify({"error": "no searchable tokens"}), 400

    corpus = _load_translation_corpus(translation)
    results: list[dict] = []
    truncated = False
    for (book, ch, v, raw_text, norm) in corpus:
        if book_filter and book != book_filter:
            continue
        # All bare tokens must appear (AND).
        if any(t not in (norm.split() if lang == "he" else norm.split(" "))
               and t not in norm for t in norm_tokens):
            continue
        if any(p not in norm for p in norm_phrases):
            continue
        # Build a snippet.
        snippet = raw_text
        if phrases:
            idx = raw_text.lower().find(phrases[0].lower())
            if idx >= 0:
                start = max(0, idx - 40)
                end = min(len(raw_text), idx + len(phrases[0]) + 40)
                snippet = ("…" if start > 0 else "") + raw_text[start:end] + ("…" if end < len(raw_text) else "")
        results.append({
            "book": book, "chapter": ch, "verse": v,
            "text": raw_text, "snippet": snippet,
        })
        if len(results) >= limit:
            truncated = True
            break
    return jsonify({
        "translation": translation, "query": qraw,
        "count": len(results), "truncated": truncated, "results": results,
    })


# --- Lemma-aware Hebrew search (#4) ---------------------------------------

# Common Hebrew prefixes attached to nouns (article, conjunction, prepositions,
# inseparable possessive). Stripping these greatly improves recall when a
# user pastes a wordform from a verse.
_HEB_PREFIXES = ("ה", "ו", "ב", "כ", "ל", "מ", "ש")
# Common pronominal suffixes that change ending letters.
_HEB_SUFFIXES = ("ים", "ות", "י", "ך", "ה", "ו", "נו", "כם", "כן", "הם", "הן")


def _hebrew_root_candidates(s: str) -> set[str]:
    """Cheap morphological reduction: strip 0–2 prefixes and an optional
    suffix to enumerate plausible roots/lemmas. Not linguistically rigorous
    but catches the common cases (ה, ו, ב, כ, ל, מ, ש prefixes; ים/ות/י/ך
    suffixes)."""
    cands = {s}
    for _ in range(2):
        nxt = set()
        for c in list(cands):
            for p in _HEB_PREFIXES:
                if len(c) > len(p) + 1 and c.startswith(p):
                    nxt.add(c[len(p):])
            cands |= nxt
        cands |= nxt
    final = set(cands)
    for c in list(cands):
        for sfx in _HEB_SUFFIXES:
            if len(c) > len(sfx) + 1 and c.endswith(sfx):
                final.add(c[:-len(sfx)])
    return final


@study_bp.route("/hebrew/lemma-search")
def hebrew_lemma_search():
    """Return verses where any morphological variant of the given Hebrew
    word appears. Computes plausible roots by trimming common prefixes and
    suffixes and matches token-by-token in the cached Hebrew corpus.
    """
    from app import _strip_hebrew_marks, _load_hebrew_corpus
    raw = (request.args.get("word") or "").strip()
    if not raw:
        return jsonify({"error": "word required"}), 400
    norm = _strip_hebrew_marks(raw).strip()
    if not norm:
        return jsonify({"error": "word has no Hebrew letters"}), 400
    try:
        limit = max(1, min(int(request.args.get("limit") or 30), 200))
    except ValueError:
        limit = 30

    roots = _hebrew_root_candidates(norm)
    samples: list[dict] = []
    total = 0
    verses_with_match = 0
    for (book, ch, v, raw_text, norm_text) in _load_hebrew_corpus():
        tokens = norm_text.split()
        hits = 0
        for tok in tokens:
            tok_roots = _hebrew_root_candidates(tok)
            if tok_roots & roots:
                hits += 1
        if not hits:
            continue
        total += hits
        verses_with_match += 1
        if len(samples) < limit:
            samples.append({
                "book": book, "chapter": ch, "verse": v,
                "text": raw_text, "hits": hits,
            })
    return jsonify({
        "word": raw, "normalized": norm, "roots": sorted(roots),
        "count": total, "verses_with_matches": verses_with_match,
        "samples": samples,
    })


# --- Cross-references (#5) ------------------------------------------------

@study_bp.route("/crossrefs/<book>/<int:chapter>/<int:verse>")
def crossrefs_for(book: str, chapter: int, verse: int):
    key = f"{book} {chapter}:{verse}"
    refs = cross_refs().get(key) or []
    return jsonify({"ref": key, "crossrefs": refs})


# --- Topic / tag system (#7) ----------------------------------------------

@study_bp.route("/me/tags", methods=["GET"])
def list_tags():
    where, params = _owner_clause()
    with _db() as c:
        rows = c.execute(
            f"""SELECT t.id, t.name, t.color, t.created_at,
                       COUNT(l.id) AS verse_count
                FROM tags t LEFT JOIN tag_links l ON l.tag_id = t.id
                WHERE {where}
                GROUP BY t.id ORDER BY t.name COLLATE NOCASE""",
            params,
        ).fetchall()
    return jsonify({"tags": [dict(r) for r in rows]})


@study_bp.route("/me/tags", methods=["POST"])
def upsert_tag():
    if not _has_owner():
        return jsonify({"ok": False, "error": "no owner"}), 400
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()[:48]
    color = (data.get("color") or "").strip()[:16] or None
    if not name:
        return jsonify({"ok": False, "error": "name required"}), 400
    uid, dk = _owner_columns()
    with _db() as c:
        existing = c.execute(
            "SELECT id FROM tags WHERE (user_id IS ? OR user_id = ?) AND "
            "(device_key IS ? OR device_key = ?) AND name = ? COLLATE NOCASE",
            (uid, uid, dk, dk, name),
        ).fetchone()
        if existing:
            c.execute("UPDATE tags SET color = COALESCE(?, color) WHERE id = ?",
                      (color, existing["id"]))
            return jsonify({"ok": True, "id": existing["id"]})
        cur = c.execute(
            "INSERT INTO tags(user_id, device_key, name, color, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (uid, dk, name, color, _now()),
        )
        return jsonify({"ok": True, "id": cur.lastrowid})


@study_bp.route("/me/tags/<int:tag_id>", methods=["DELETE"])
def delete_tag(tag_id: int):
    where, params = _owner_clause()
    with _db() as c:
        cur = c.execute(f"DELETE FROM tags WHERE id = ? AND {where}",
                        (tag_id, *params))
    return jsonify({"ok": cur.rowcount > 0})


@study_bp.route("/me/tags/<int:tag_id>/verses", methods=["GET"])
def list_tag_verses(tag_id: int):
    where, params = _owner_clause()
    with _db() as c:
        # Validate ownership.
        own = c.execute(f"SELECT id FROM tags WHERE id = ? AND {where}",
                        (tag_id, *params)).fetchone()
        if not own:
            return jsonify({"error": "not found"}), 404
        rows = c.execute(
            "SELECT id, book, chapter, verse, created_at FROM tag_links "
            "WHERE tag_id = ? ORDER BY book, chapter, verse", (tag_id,),
        ).fetchall()
    return jsonify({"verses": [dict(r) for r in rows]})


@study_bp.route("/me/tag-link", methods=["POST"])
def link_tag():
    if not _has_owner():
        return jsonify({"ok": False, "error": "no owner"}), 400
    data = request.get_json(silent=True) or {}
    tag_id = data.get("tag_id")
    book = (data.get("book") or "").strip()
    try:
        chapter, verse = int(data.get("chapter")), int(data.get("verse"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "bad ref"}), 400
    if book not in ALL_BOOKS:
        return jsonify({"ok": False, "error": "unknown book"}), 400
    where, params = _owner_clause()
    with _db() as c:
        own = c.execute(f"SELECT id FROM tags WHERE id = ? AND {where}",
                        (tag_id, *params)).fetchone()
        if not own:
            return jsonify({"ok": False, "error": "tag not yours"}), 404
        try:
            c.execute(
                "INSERT INTO tag_links(tag_id, book, chapter, verse, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (tag_id, book, chapter, verse, _now()),
            )
        except sqlite3.IntegrityError:
            pass  # Already linked.
    return jsonify({"ok": True})


@study_bp.route("/me/tag-link/<int:tag_id>/<book>/<int:chapter>/<int:verse>",
                methods=["DELETE"])
def unlink_tag(tag_id: int, book: str, chapter: int, verse: int):
    where, params = _owner_clause()
    with _db() as c:
        own = c.execute(f"SELECT id FROM tags WHERE id = ? AND {where}",
                        (tag_id, *params)).fetchone()
        if not own:
            return jsonify({"ok": False}), 404
        cur = c.execute(
            "DELETE FROM tag_links WHERE tag_id = ? AND book = ? AND "
            "chapter = ? AND verse = ?",
            (tag_id, book, chapter, verse),
        )
    return jsonify({"ok": cur.rowcount > 0})


# --- Sermon outlines (#6) -------------------------------------------------

@study_bp.route("/me/outlines", methods=["GET"])
def list_outlines():
    where, params = _owner_clause()
    with _db() as c:
        rows = c.execute(
            f"""SELECT id, title, theme, updated_at, created_at
                FROM outlines WHERE {where} ORDER BY updated_at DESC""",
            params,
        ).fetchall()
    return jsonify({"outlines": [dict(r) for r in rows]})


@study_bp.route("/me/outlines", methods=["POST"])
def create_outline():
    if not _has_owner():
        return jsonify({"ok": False, "error": "no owner"}), 400
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Untitled outline").strip()[:160]
    theme = (data.get("theme") or "").strip()[:280] or None
    body = (data.get("body_md") or "").strip()
    uid, dk = _owner_columns()
    now = _now()
    with _db() as c:
        cur = c.execute(
            "INSERT INTO outlines(user_id, device_key, title, theme, body_md, "
            "updated_at, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (uid, dk, title, theme, body, now, now),
        )
    return jsonify({"ok": True, "id": cur.lastrowid})


@study_bp.route("/me/outlines/<int:oid>", methods=["GET"])
def get_outline(oid: int):
    where, params = _owner_clause()
    with _db() as c:
        row = c.execute(
            f"SELECT * FROM outlines WHERE id = ? AND {where}",
            (oid, *params),
        ).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        verses = c.execute(
            "SELECT ord, book, chapter, verse, label FROM outline_verses "
            "WHERE outline_id = ? ORDER BY ord",
            (oid,),
        ).fetchall()
    return jsonify({"outline": {**dict(row), "verses": [dict(v) for v in verses]}})


@study_bp.route("/me/outlines/<int:oid>", methods=["PUT", "POST"])
def update_outline(oid: int):
    where, params = _owner_clause()
    data = request.get_json(silent=True) or {}
    fields = []
    vals: list = []
    for col in ("title", "theme", "body_md"):
        if col in data:
            fields.append(f"{col} = ?")
            v = data[col]
            if isinstance(v, str):
                v = v.strip()
            vals.append(v if v != "" else None)
    if not fields and "verses" not in data:
        return jsonify({"ok": True})
    with _db() as c:
        own = c.execute(f"SELECT id FROM outlines WHERE id = ? AND {where}",
                        (oid, *params)).fetchone()
        if not own:
            return jsonify({"ok": False, "error": "not found"}), 404
        if fields:
            fields.append("updated_at = ?")
            vals.append(_now())
            c.execute(f"UPDATE outlines SET {', '.join(fields)} WHERE id = ?",
                      (*vals, oid))
        if isinstance(data.get("verses"), list):
            c.execute("DELETE FROM outline_verses WHERE outline_id = ?", (oid,))
            for i, v in enumerate(data["verses"]):
                if not isinstance(v, dict):
                    continue
                book = (v.get("book") or "").strip()
                if book not in ALL_BOOKS:
                    continue
                try:
                    ch = int(v.get("chapter"))
                    vs = int(v.get("verse"))
                except (TypeError, ValueError):
                    continue
                lbl = (v.get("label") or "").strip()[:160] or None
                c.execute(
                    "INSERT INTO outline_verses(outline_id, ord, book, chapter, "
                    "verse, label) VALUES (?, ?, ?, ?, ?, ?)",
                    (oid, i, book, ch, vs, lbl),
                )
    return jsonify({"ok": True})


@study_bp.route("/me/outlines/<int:oid>", methods=["DELETE"])
def delete_outline(oid: int):
    where, params = _owner_clause()
    with _db() as c:
        cur = c.execute(f"DELETE FROM outlines WHERE id = ? AND {where}",
                        (oid, *params))
    return jsonify({"ok": cur.rowcount > 0})


@study_bp.route("/me/outlines/<int:oid>/export")
def export_outline(oid: int):
    """Markdown export of an outline with verse text inlined."""
    import bible_fetcher
    where, params = _owner_clause()
    translation = (request.args.get("translation") or "NIV").strip()
    with _db() as c:
        row = c.execute(f"SELECT * FROM outlines WHERE id = ? AND {where}",
                        (oid, *params)).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        verses = c.execute(
            "SELECT book, chapter, verse, label FROM outline_verses "
            "WHERE outline_id = ? ORDER BY ord", (oid,),
        ).fetchall()
    lines = [f"# {row['title']}"]
    if row["theme"]:
        lines += ["", f"*{row['theme']}*"]
    lines += ["", row["body_md"] or "", ""]
    if verses:
        lines += ["## Passages", ""]
        for v in verses:
            ref = f"{v['book']} {v['chapter']}:{v['verse']}"
            lines.append(f"### {ref}")
            if v["label"]:
                lines += ["", f"*{v['label']}*"]
            try:
                ch = bible_fetcher.get_verses(translation, v["book"], v["chapter"]) or {}
                txt = (ch.get(str(v["verse"])) or ch.get(int(v["verse"])) or "").strip()
                if txt:
                    lines += ["", f"> {txt}"]
            except Exception:
                pass  # verse text optional in outline export; continue
            lines.append("")
    body = "\n".join(lines) + "\n"
    safe = re.sub(r"[^a-z0-9]+", "-", row["title"].lower()).strip("-") or "outline"
    resp = Response(body, mimetype="text/markdown; charset=utf-8")
    resp.headers["Content-Disposition"] = f'attachment; filename="{safe}.md"'
    return resp


# --- Verse playlists + preach view (#8) -----------------------------------

@study_bp.route("/me/playlists", methods=["GET"])
def list_playlists():
    where, params = _owner_clause()
    with _db() as c:
        rows = c.execute(
            f"""SELECT p.id, p.title, p.description, p.created_at,
                       COUNT(i.id) AS item_count
                FROM playlists p LEFT JOIN playlist_items i
                       ON i.playlist_id = p.id
                WHERE {where} GROUP BY p.id ORDER BY p.created_at DESC""",
            params,
        ).fetchall()
    return jsonify({"playlists": [dict(r) for r in rows]})


@study_bp.route("/me/playlists", methods=["POST"])
def create_playlist():
    if not _has_owner():
        return jsonify({"ok": False, "error": "no owner"}), 400
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Untitled playlist").strip()[:160]
    desc = (data.get("description") or "").strip()[:1000] or None
    uid, dk = _owner_columns()
    with _db() as c:
        cur = c.execute(
            "INSERT INTO playlists(user_id, device_key, title, description, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, dk, title, desc, _now()),
        )
    return jsonify({"ok": True, "id": cur.lastrowid})


@study_bp.route("/me/playlists/<int:pid>", methods=["GET"])
def get_playlist(pid: int):
    where, params = _owner_clause()
    with _db() as c:
        row = c.execute(
            f"SELECT * FROM playlists WHERE id = ? AND {where}",
            (pid, *params),
        ).fetchone()
        if not row:
            return jsonify({"error": "not found"}), 404
        items = c.execute(
            "SELECT id, ord, book, chapter, verse_start, verse_end, note "
            "FROM playlist_items WHERE playlist_id = ? ORDER BY ord", (pid,),
        ).fetchall()
    return jsonify({"playlist": {**dict(row), "items": [dict(i) for i in items]}})


@study_bp.route("/me/playlists/<int:pid>/items", methods=["POST"])
def add_playlist_item(pid: int):
    where, params = _owner_clause()
    data = request.get_json(silent=True) or {}
    book = (data.get("book") or "").strip()
    if book not in ALL_BOOKS:
        return jsonify({"ok": False, "error": "unknown book"}), 400
    try:
        ch = int(data.get("chapter"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "chapter required"}), 400
    vs = data.get("verse_start")
    ve = data.get("verse_end")
    try:
        vs = int(vs) if vs is not None else None
        ve = int(ve) if ve is not None else None
    except (TypeError, ValueError):
        vs, ve = None, None
    note = (data.get("note") or "").strip()[:280] or None
    with _db() as c:
        own = c.execute(f"SELECT id FROM playlists WHERE id = ? AND {where}",
                        (pid, *params)).fetchone()
        if not own:
            return jsonify({"ok": False}), 404
        n = c.execute("SELECT COALESCE(MAX(ord), -1) + 1 AS n FROM playlist_items "
                      "WHERE playlist_id = ?", (pid,)).fetchone()["n"]
        cur = c.execute(
            "INSERT INTO playlist_items(playlist_id, ord, book, chapter, "
            "verse_start, verse_end, note) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (pid, n, book, ch, vs, ve, note),
        )
    return jsonify({"ok": True, "id": cur.lastrowid})


@study_bp.route("/me/playlists/<int:pid>/items/<int:item_id>", methods=["DELETE"])
def delete_playlist_item(pid: int, item_id: int):
    where, params = _owner_clause()
    with _db() as c:
        own = c.execute(f"SELECT id FROM playlists WHERE id = ? AND {where}",
                        (pid, *params)).fetchone()
        if not own:
            return jsonify({"ok": False}), 404
        cur = c.execute("DELETE FROM playlist_items WHERE id = ? AND playlist_id = ?",
                        (item_id, pid))
    return jsonify({"ok": cur.rowcount > 0})


@study_bp.route("/me/playlists/<int:pid>", methods=["DELETE"])
def delete_playlist(pid: int):
    where, params = _owner_clause()
    with _db() as c:
        cur = c.execute(f"DELETE FROM playlists WHERE id = ? AND {where}",
                        (pid, *params))
    return jsonify({"ok": cur.rowcount > 0})


# --- Reading plan engine (#9) ---------------------------------------------

@study_bp.route("/plans")
def list_plans():
    return jsonify({"plans": [
        {"slug": s, "title": p["title"], "summary": p["summary"]}
        for s, p in _PLANS.items()
    ]})


@study_bp.route("/plans/<slug>")
def plan_detail(slug: str):
    plan = get_plan(slug)
    if not plan:
        return jsonify({"error": "unknown plan"}), 404
    return jsonify(plan)


@study_bp.route("/me/plans/<slug>/progress", methods=["GET"])
def get_progress(slug: str):
    where, params = _owner_clause()
    with _db() as c:
        rows = c.execute(
            f"SELECT day, completed_at FROM plan_progress "
            f"WHERE {where} AND plan_slug = ? ORDER BY day",
            (*params, slug),
        ).fetchall()
    return jsonify({"plan": slug, "completed_days": [r["day"] for r in rows]})


@study_bp.route("/me/plans/<slug>/progress", methods=["POST"])
def mark_day(slug: str):
    if not _has_owner():
        return jsonify({"ok": False}), 400
    data = request.get_json(silent=True) or {}
    try:
        day = int(data.get("day"))
    except (TypeError, ValueError):
        return jsonify({"ok": False, "error": "day required"}), 400
    completed = bool(data.get("completed", True))
    uid, dk = _owner_columns()
    with _db() as c:
        if completed:
            try:
                c.execute(
                    "INSERT INTO plan_progress(user_id, device_key, plan_slug, "
                    "day, completed_at) VALUES (?, ?, ?, ?, ?)",
                    (uid, dk, slug, day, _now()),
                )
            except sqlite3.IntegrityError:
                pass
        else:
            where, params = _owner_clause()
            c.execute(
                f"DELETE FROM plan_progress WHERE {where} AND plan_slug = ? AND day = ?",
                (*params, slug, day),
            )
    return jsonify({"ok": True})


# --- Inline interlinear (#11) — backed by Hebrew dictionary ---------------

@study_bp.route("/interlinear/<book>/<int:chapter>")
def interlinear(book: str, chapter: int):
    """Return per-token Hebrew→gloss data for the chapter, when available."""
    import bible_fetcher
    from app import _load_hebrew_dict, _strip_hebrew_marks
    if book not in ALL_BOOKS:
        return jsonify({"error": "unknown book"}), 404
    verses = bible_fetcher.get_verses("Hebrew", book, chapter) or {}
    if not verses:
        return jsonify({"verses": {}})
    direct, norm_map = _load_hebrew_dict()
    out: dict = {}
    for vk, vt in verses.items():
        tokens = []
        for tok in (vt or "").split():
            n = _strip_hebrew_marks(tok).strip(",.;:!?\u05BE")
            gloss = direct.get(tok) or (norm_map.get(n) or (None, None))[1] if n else None
            tokens.append({"t": tok, "g": gloss})
        out[str(vk)] = tokens
    return jsonify({"book": book, "chapter": chapter, "verses": out})


# --- Footnotes drawer (#15) — endpoint stub w/ extensible JSON file -------

@study_bp.route("/footnotes/<book>/<int:chapter>")
def footnotes(book: str, chapter: int):
    """Return any footnotes shipped under data/footnotes/<book>/<ch>.json."""
    if book not in ALL_BOOKS:
        return jsonify({"error": "unknown book"}), 404
    base = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "data", "footnotes",
        ALL_BOOKS[book]["slug"],
    )
    path = os.path.join(base, f"{chapter}.json")
    if not os.path.exists(path):
        return jsonify({"verses": {}})
    try:
        with open(path, "r", encoding="utf-8") as f:
            return jsonify({"verses": json.load(f)})
    except Exception:
        return jsonify({"verses": {}})


# --- Pronunciation cache (#14) --------------------------------------------

_TTS_CACHE_DIR = None


def _tts_cache_dir() -> str:
    global _TTS_CACHE_DIR
    if _TTS_CACHE_DIR is None:
        d = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "data", "tts-cache",
        )
        os.makedirs(d, exist_ok=True)
        _TTS_CACHE_DIR = d
    return _TTS_CACHE_DIR


def tts_cache_lookup(text: str, lang: str, voice: str) -> Optional[bytes]:
    key = hashlib.sha256(f"{lang}|{voice}|{text}".encode("utf-8")).hexdigest()
    path = os.path.join(_tts_cache_dir(), key + ".mp3")
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                return f.read()
        except Exception as exc:  # pragma: no cover
            logger.debug("tts cache read failed for %s: %s", key, exc)
            return None
    return None


def tts_cache_store(text: str, lang: str, voice: str, mp3: bytes) -> None:
    if not mp3:
        return
    key = hashlib.sha256(f"{lang}|{voice}|{text}".encode("utf-8")).hexdigest()
    path = os.path.join(_tts_cache_dir(), key + ".mp3")
    try:
        with open(path, "wb") as f:
            f.write(mp3)
    except Exception as exc:  # pragma: no cover
        logger.warning("tts cache store failed for %s: %s", key, exc)


# --- Audio clip export (#13) ----------------------------------------------

@study_bp.route("/clip")
def audio_clip():
    """Return a single MP3 covering a verse range (concatenated TTS)."""
    from app import _synthesize_edge, DEFAULT_EDGE_VOICE, EDGE_VOICE_NAMES
    import bible_fetcher

    book = (request.args.get("book") or "").strip()
    if book not in ALL_BOOKS:
        return jsonify({"error": "unknown book"}), 400
    try:
        chapter = int(request.args.get("chapter"))
        v_from = int(request.args.get("from"))
        v_to = int(request.args.get("to") or v_from)
    except (TypeError, ValueError):
        return jsonify({"error": "chapter/from/to required"}), 400
    if v_to < v_from:
        v_from, v_to = v_to, v_from
    if v_to - v_from > 30:
        return jsonify({"error": "max 30 verses per clip"}), 400
    translation = (request.args.get("translation") or "NIV").strip()
    voice = (request.args.get("voice") or "").strip()
    lang = "he" if translation == "Hebrew" else (
        "hu" if translation.startswith("Hungarian") else "en")
    if voice not in EDGE_VOICE_NAMES:
        voice = DEFAULT_EDGE_VOICE.get(lang) or DEFAULT_EDGE_VOICE["en"]

    verses = bible_fetcher.get_verses(translation, book, chapter) or {}
    parts = []
    for v in range(v_from, v_to + 1):
        txt = (verses.get(str(v)) or verses.get(v) or "").strip()
        if not txt:
            continue
        # Strip cantillation/nikud — same sanitization the /api/tts uses.
        txt = re.sub(r"[\u200B-\u200F\u202A-\u202E\uFEFF]", "", txt)
        txt = re.sub(r"[\u0591-\u05AF]", "", txt)
        cached = tts_cache_lookup(txt, lang, voice)
        if cached:
            parts.append(cached)
            continue
        try:
            mp3 = _synthesize_edge(txt, voice)
        except Exception as e:
            current_app.logger.warning("clip TTS failed v=%s: %s", v, e)
            continue
        tts_cache_store(txt, lang, voice, mp3)
        parts.append(mp3)
    if not parts:
        return jsonify({"error": "no audio produced"}), 500
    body = b"".join(parts)
    fn = f"{book.replace(' ', '-').lower()}-{chapter}-{v_from}-{v_to}.mp3"
    resp = Response(body, mimetype="audio/mpeg")
    resp.headers["Content-Disposition"] = f'attachment; filename="{fn}"'
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


# --- Shared notebooks (#16) -----------------------------------------------

def _user_id() -> Optional[int]:
    from flask import g
    user = g.get("current_user") or {}
    return user.get("id")


def _is_notebook_member(c, nb_id: int, uid: int) -> bool:
    row = c.execute("SELECT id FROM notebooks WHERE id = ? AND user_id = ?",
                    (nb_id, uid)).fetchone()
    if row:
        return True
    row = c.execute("SELECT id FROM notebook_members WHERE notebook_id = ? AND user_id = ?",
                    (nb_id, uid)).fetchone()
    return bool(row)


@study_bp.route("/me/notebooks", methods=["GET"])
def list_notebooks():
    uid = _user_id()
    if uid is None:
        return jsonify({"notebooks": [], "needs_login": True})
    with _db() as c:
        rows = c.execute(
            """SELECT n.id, n.title, n.description, n.share_token, n.created_at,
                      (SELECT COUNT(*) FROM notebook_members m
                         WHERE m.notebook_id = n.id) AS member_count,
                      (n.user_id = ?) AS is_owner
               FROM notebooks n
               WHERE n.user_id = ? OR n.id IN
                     (SELECT notebook_id FROM notebook_members WHERE user_id = ?)
               ORDER BY n.created_at DESC""",
            (uid, uid, uid),
        ).fetchall()
    return jsonify({"notebooks": [dict(r) for r in rows]})


@study_bp.route("/me/notebooks", methods=["POST"])
def create_notebook():
    uid = _user_id()
    if uid is None:
        return jsonify({"ok": False, "needs_login": True}), 401
    data = request.get_json(silent=True) or {}
    title = (data.get("title") or "Untitled notebook").strip()[:160]
    desc = (data.get("description") or "").strip()[:2000] or None
    token = secrets.token_urlsafe(16)
    with _db() as c:
        cur = c.execute(
            "INSERT INTO notebooks(user_id, title, description, share_token, "
            "created_at) VALUES (?, ?, ?, ?, ?)",
            (uid, title, desc, token, _now()),
        )
    return jsonify({"ok": True, "id": cur.lastrowid, "share_token": token})


@study_bp.route("/me/notebooks/<int:nb_id>")
def notebook_detail(nb_id: int):
    uid = _user_id()
    if uid is None:
        return jsonify({"needs_login": True}), 401
    with _db() as c:
        nb = c.execute("SELECT * FROM notebooks WHERE id = ?", (nb_id,)).fetchone()
        if not nb or not _is_notebook_member(c, nb_id, uid):
            return jsonify({"error": "not found"}), 404
        entries = c.execute(
            """SELECT e.*, u.email AS author_email
               FROM notebook_entries e LEFT JOIN users u ON u.id = e.user_id
               WHERE e.notebook_id = ? ORDER BY e.created_at DESC LIMIT 200""",
            (nb_id,),
        ).fetchall()
    return jsonify({"notebook": dict(nb), "entries": [dict(e) for e in entries]})


@study_bp.route("/me/notebooks/<int:nb_id>/entries", methods=["POST"])
def add_entry(nb_id: int):
    uid = _user_id()
    if uid is None:
        return jsonify({"needs_login": True}), 401
    data = request.get_json(silent=True) or {}
    body = (data.get("body_md") or "").strip()
    if not body:
        return jsonify({"ok": False, "error": "body_md required"}), 400
    book = (data.get("book") or "").strip() or None
    chapter = data.get("chapter")
    verse = data.get("verse")
    try:
        chapter = int(chapter) if chapter else None
        verse = int(verse) if verse else None
    except (TypeError, ValueError):
        chapter, verse = None, None
    with _db() as c:
        if not _is_notebook_member(c, nb_id, uid):
            return jsonify({"error": "not found"}), 404
        cur = c.execute(
            "INSERT INTO notebook_entries(notebook_id, user_id, book, chapter, "
            "verse, body_md, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (nb_id, uid, book, chapter, verse, body, _now()),
        )
    return jsonify({"ok": True, "id": cur.lastrowid})


@study_bp.route("/notebooks/join/<token>", methods=["POST"])
def join_notebook(token: str):
    uid = _user_id()
    if uid is None:
        return jsonify({"needs_login": True}), 401
    with _db() as c:
        nb = c.execute("SELECT id, user_id FROM notebooks WHERE share_token = ?",
                       (token,)).fetchone()
        if not nb:
            return jsonify({"ok": False, "error": "invalid link"}), 404
        if nb["user_id"] != uid:
            try:
                c.execute(
                    "INSERT INTO notebook_members(notebook_id, user_id, role, joined_at) "
                    "VALUES (?, ?, 'member', ?)",
                    (nb["id"], uid, _now()),
                )
            except sqlite3.IntegrityError:
                pass
    return jsonify({"ok": True, "notebook_id": nb["id"]})


# --- OG share image (#17) -------------------------------------------------

@study_bp.route("/share/verse.png")
def share_verse_png():
    """Render a 1200×630 PNG containing a verse + reference for social cards.

    Falls back to plain SVG (returned as image/svg+xml) when Pillow isn't
    available, so the feature works out of the box.
    """
    text = (request.args.get("text") or "").strip()
    ref = (request.args.get("ref") or "").strip()
    if not text or not ref:
        return jsonify({"error": "text and ref required"}), 400
    text = text[:480]
    ref = ref[:80]

    def _svg_card() -> Response:
        # Word-wrap text by character count for the SVG fallback.
        import textwrap
        body = "\n".join(textwrap.wrap(text, width=46))
        # Each line as a tspan.
        tspans = "".join(
            f'<tspan x="600" dy="{0 if i == 0 else 56}">{_xml(line)}</tspan>'
            for i, line in enumerate(body.split("\n")[:8])
        )
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 630">
<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">
<stop offset="0%" stop-color="#1f2937"/><stop offset="100%" stop-color="#0b3a66"/>
</linearGradient></defs>
<rect width="1200" height="630" fill="url(#g)"/>
<text x="600" y="220" fill="#ffffff" font-family="Georgia, serif" font-size="48"
      text-anchor="middle">{tspans}</text>
<text x="600" y="560" fill="#fbbf24" font-family="Inter, sans-serif" font-size="38"
      font-weight="600" text-anchor="middle">{_xml(ref)}</text>
<text x="600" y="600" fill="#cbd5e1" font-family="Inter, sans-serif" font-size="22"
      text-anchor="middle">RITDorg Bible Reader</text>
</svg>'''
        return Response(svg, mimetype="image/svg+xml")

    try:
        from PIL import Image, ImageDraw, ImageFont  # type: ignore
    except Exception:
        return _svg_card()
    try:
        img = Image.new("RGB", (1200, 630), (15, 23, 42))
        # Background gradient fallback (stripes; simple).
        d = ImageDraw.Draw(img)
        for y in range(630):
            t = y / 629
            r = int(31 * (1 - t) + 11 * t)
            g = int(41 * (1 - t) + 58 * t)
            b = int(55 * (1 - t) + 102 * t)
            d.line([(0, y), (1200, y)], fill=(r, g, b))
        try:
            font_body = ImageFont.truetype("/System/Library/Fonts/Supplemental/Georgia.ttf", 44)
            font_ref = ImageFont.truetype("/System/Library/Fonts/Supplemental/Verdana Bold.ttf", 36)
            font_brand = ImageFont.truetype("/System/Library/Fonts/Supplemental/Verdana.ttf", 22)
        except Exception:
            font_body = ImageFont.load_default()
            font_ref = ImageFont.load_default()
            font_brand = ImageFont.load_default()
        # Word-wrap.
        import textwrap
        body_lines = textwrap.wrap(text, width=42)[:8]
        y = 200
        for ln in body_lines:
            w = d.textlength(ln, font=font_body)
            d.text(((1200 - w) / 2, y), ln, fill=(255, 255, 255), font=font_body)
            y += 54
        wref = d.textlength(ref, font=font_ref)
        d.text(((1200 - wref) / 2, 540), ref, fill=(251, 191, 36), font=font_ref)
        brand = "RITDorg Bible Reader"
        wb = d.textlength(brand, font=font_brand)
        d.text(((1200 - wb) / 2, 590), brand, fill=(203, 213, 225), font=font_brand)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return Response(buf.getvalue(), mimetype="image/png",
                        headers={"Cache-Control": "public, max-age=86400"})
    except Exception:
        return _svg_card()


def _xml(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# --- Full export ZIP (#19) ------------------------------------------------

@study_bp.route("/me/export/all")
def export_all():
    """A single ZIP with notes, bookmarks, highlights, tags, outlines,
    playlists, plan progress, and settings — Markdown + JSON."""
    where, params = _owner_clause()
    if not _has_owner():
        return jsonify({"error": "no owner"}), 401
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        # Notes.
        zf.writestr("notes.json", json.dumps(auth.list_notes(), indent=2))
        zf.writestr("bookmarks.json", json.dumps(auth.list_bookmarks(), indent=2))
        zf.writestr("highlights.json", json.dumps(auth.list_highlights(), indent=2))
        # Tags + tag links.
        with _db() as c:
            tag_rows = [dict(r) for r in c.execute(
                f"SELECT id, name, color, created_at FROM tags WHERE {where}",
                params,
            ).fetchall()]
            tag_ids = [t["id"] for t in tag_rows]
            tag_links: list = []
            if tag_ids:
                qmarks = ",".join("?" * len(tag_ids))
                tag_links = [dict(r) for r in c.execute(
                    f"SELECT * FROM tag_links WHERE tag_id IN ({qmarks})",
                    tag_ids,
                ).fetchall()]
            zf.writestr("tags.json", json.dumps({"tags": tag_rows, "links": tag_links}, indent=2))
            # Outlines.
            outlines = [dict(r) for r in c.execute(
                f"SELECT * FROM outlines WHERE {where}", params,
            ).fetchall()]
            for o in outlines:
                o["verses"] = [dict(v) for v in c.execute(
                    "SELECT * FROM outline_verses WHERE outline_id = ? ORDER BY ord",
                    (o["id"],),
                ).fetchall()]
            zf.writestr("outlines.json", json.dumps(outlines, indent=2))
            # Playlists.
            playlists = [dict(r) for r in c.execute(
                f"SELECT * FROM playlists WHERE {where}", params,
            ).fetchall()]
            for p in playlists:
                p["items"] = [dict(i) for i in c.execute(
                    "SELECT * FROM playlist_items WHERE playlist_id = ? ORDER BY ord",
                    (p["id"],),
                ).fetchall()]
            zf.writestr("playlists.json", json.dumps(playlists, indent=2))
            progress = [dict(r) for r in c.execute(
                f"SELECT plan_slug, day, completed_at FROM plan_progress WHERE {where}",
                params,
            ).fetchall()]
            zf.writestr("reading-progress.json", json.dumps(progress, indent=2))
            settings = [dict(r) for r in c.execute(
                f"SELECT key, value FROM settings WHERE {where}", params,
            ).fetchall()]
            zf.writestr("settings.json", json.dumps(settings, indent=2))
        zf.writestr("README.txt",
                    "RITDorg user data export.\n"
                    f"Generated: {_now()}\n"
                    "Files: notes/bookmarks/highlights/tags/outlines/playlists/"
                    "reading-progress/settings.\n")
    buf.seek(0)
    return send_file(
        buf, mimetype="application/zip", as_attachment=True,
        download_name=f"ritdorg-export-{int(time.time())}.zip",
    )


# --- Settings store (used by permalink/dyslexia/etc) (#18, #22) ----------

@study_bp.route("/me/settings", methods=["GET"])
def list_settings():
    where, params = _owner_clause()
    with _db() as c:
        rows = c.execute(f"SELECT key, value FROM settings WHERE {where}",
                         params).fetchall()
    return jsonify({"settings": {r["key"]: r["value"] for r in rows}})


@study_bp.route("/me/settings", methods=["POST", "PUT"])
def upsert_settings():
    if not _has_owner():
        return jsonify({"ok": False, "error": "no owner"}), 400
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify({"ok": False}), 400
    uid, dk = _owner_columns()
    where, params = _owner_clause()
    with _db() as c:
        for k, v in data.items():
            k = str(k)[:64]
            v = None if v is None else str(v)[:1024]
            c.execute(
                f"DELETE FROM settings WHERE {where} AND key = ?",
                (*params, k),
            )
            c.execute(
                "INSERT INTO settings(user_id, device_key, key, value) "
                "VALUES (?, ?, ?, ?)",
                (uid, dk, k, v),
            )
    return jsonify({"ok": True})


# --- Greek NT scaffolding (#24) -------------------------------------------
# We don't ship Greek text yet, but expose a discovery endpoint so the
# client can detect availability when the corpus is added under
# static/data/bible/sblgnt/.

@study_bp.route("/corpus/availability")
def corpus_availability():
    base = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "static", "data", "bible",
    )
    out = {}
    for slug in ("sblgnt", "byz"):
        path = os.path.join(base, slug)
        out[slug] = os.path.isdir(path)
    return jsonify({"available": out})


# --- Timeline / book metadata (#12) ---------------------------------------

# Compact bundled metadata for the timeline/map panel. Dates are very
# rough scholarly estimates; the goal is orientation, not precision.
_BOOK_META = {
    "Genesis":        {"era": "Patriarchs",       "date_bc": -1400, "place": "Mesopotamia / Canaan"},
    "Exodus":         {"era": "Exodus",           "date_bc": -1400, "place": "Egypt → Sinai"},
    "Leviticus":      {"era": "Wilderness",       "date_bc": -1400, "place": "Sinai"},
    "Numbers":        {"era": "Wilderness",       "date_bc": -1400, "place": "Sinai → Moab"},
    "Deuteronomy":    {"era": "Wilderness",       "date_bc": -1400, "place": "Plains of Moab"},
    "Joshua":         {"era": "Conquest",         "date_bc": -1380, "place": "Canaan"},
    "Judges":         {"era": "Judges",           "date_bc": -1100, "place": "Canaan"},
    "Ruth":           {"era": "Judges",           "date_bc": -1100, "place": "Bethlehem / Moab"},
    "1 Samuel":       {"era": "United monarchy",  "date_bc": -1050, "place": "Israel"},
    "2 Samuel":       {"era": "United monarchy",  "date_bc": -1000, "place": "Israel"},
    "1 Kings":        {"era": "Monarchy",         "date_bc": -950,  "place": "Israel"},
    "2 Kings":        {"era": "Monarchy",         "date_bc": -800,  "place": "Israel/Judah"},
    "Psalms":         {"era": "Monarchy",         "date_bc": -1000, "place": "Israel"},
    "Proverbs":       {"era": "Monarchy",         "date_bc": -950,  "place": "Israel"},
    "Isaiah":         {"era": "Pre-exile",        "date_bc": -700,  "place": "Judah"},
    "Jeremiah":       {"era": "Exile",            "date_bc": -600,  "place": "Judah/Egypt"},
    "Ezekiel":        {"era": "Exile",            "date_bc": -580,  "place": "Babylon"},
    "Daniel":         {"era": "Exile",            "date_bc": -560,  "place": "Babylon"},
    "Ezra":           {"era": "Return",           "date_bc": -450,  "place": "Jerusalem"},
    "Nehemiah":       {"era": "Return",           "date_bc": -440,  "place": "Jerusalem"},
    "Matthew":        {"era": "Gospels",          "date_bc": 50,    "place": "Israel"},
    "Mark":           {"era": "Gospels",          "date_bc": 60,    "place": "Rome"},
    "Luke":           {"era": "Gospels",          "date_bc": 65,    "place": "Greece/Rome"},
    "John":           {"era": "Gospels",          "date_bc": 90,    "place": "Ephesus"},
    "Acts":           {"era": "Apostolic",        "date_bc": 65,    "place": "Mediterranean"},
    "Romans":         {"era": "Apostolic",        "date_bc": 57,    "place": "Corinth → Rome"},
    "Revelation":     {"era": "Apostolic",        "date_bc": 95,    "place": "Patmos"},
}


@study_bp.route("/timeline")
def timeline():
    out = []
    for book in ALL_BOOKS:
        meta = _BOOK_META.get(book)
        if meta:
            out.append({"book": book, **meta})
    return jsonify({"books": out})
