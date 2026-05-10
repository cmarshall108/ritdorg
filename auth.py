"""User auth: optional email capture, 1-week sessions, SQLite storage.

Schema (SQLite, single file at AUTH_DB_PATH):

    users(id, email UNIQUE, created_at, last_seen_at)
    sessions(token PK, user_id FK, created_at, expires_at, ip, user_agent)

All timestamps are ISO 8601 UTC strings.

Email is *optional* - visitors can browse the site freely. When they share
an email, we save it and set a 7-day session cookie so we recognise them.
"""

from __future__ import annotations

import os
import re
import secrets
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Optional

from flask import g, request, session


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

AUTH_DB_PATH = os.environ.get(
    "AUTH_DB_PATH",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "auth.db"),
)

SESSION_COOKIE_NAME = "ritd_session"
DISMISS_COOKIE_NAME = "ritd_email_dismissed"
DEVICE_COOKIE_NAME  = "ritd_device"
SESSION_DURATION = timedelta(days=7)
DISMISS_DURATION = timedelta(days=30)
DEVICE_DURATION  = timedelta(days=365 * 2)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse(iso_str: str) -> datetime:
    return datetime.fromisoformat(iso_str)


@contextmanager
def _connect():
    os.makedirs(os.path.dirname(AUTH_DB_PATH), exist_ok=True)
    conn = sqlite3.connect(AUTH_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Create tables if they don't exist. Safe to call repeatedly."""
    with _connect() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                email        TEXT UNIQUE NOT NULL,
                created_at   TEXT NOT NULL,
                last_seen_at TEXT
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token       TEXT PRIMARY KEY,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at  TEXT NOT NULL,
                expires_at  TEXT NOT NULL,
                ip          TEXT,
                user_agent  TEXT
            );
            CREATE INDEX IF NOT EXISTS sessions_user_idx ON sessions(user_id);

            -- Per-visitor reading state (last position, view mode, prefs).
            -- Owner is identified by either user_id (logged in) or
            -- device_key (anonymous cookie). Exactly one of these is set.
            CREATE TABLE IF NOT EXISTS reading_state (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                book        TEXT,
                chapter     INTEGER,
                verse       INTEGER,
                view        TEXT,
                updated_at  TEXT NOT NULL,
                UNIQUE(user_id),
                UNIQUE(device_key)
            );

            CREATE TABLE IF NOT EXISTS bookmarks (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                book        TEXT NOT NULL,
                chapter     INTEGER NOT NULL,
                verse       INTEGER NOT NULL,
                label       TEXT,
                created_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS bookmarks_owner_idx
                ON bookmarks(user_id, device_key);

            CREATE TABLE IF NOT EXISTS notes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                book        TEXT NOT NULL,
                chapter     INTEGER NOT NULL,
                verse       INTEGER NOT NULL,
                body        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS notes_owner_idx
                ON notes(user_id, device_key);
            CREATE INDEX IF NOT EXISTS notes_loc_idx
                ON notes(book, chapter);

            CREATE TABLE IF NOT EXISTS highlights (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER REFERENCES users(id) ON DELETE CASCADE,
                device_key  TEXT,
                book        TEXT NOT NULL,
                chapter     INTEGER NOT NULL,
                verse       INTEGER NOT NULL,
                color       TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                UNIQUE(user_id, book, chapter, verse),
                UNIQUE(device_key, book, chapter, verse)
            );
            CREATE INDEX IF NOT EXISTS highlights_owner_idx
                ON highlights(user_id, device_key);
            """
        )


# ---------------------------------------------------------------------------
# Email validation
# ---------------------------------------------------------------------------

def normalize_email(email: str) -> Optional[str]:
    if not email:
        return None
    email = email.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        return None
    return email


# ---------------------------------------------------------------------------
# Users + sessions
# ---------------------------------------------------------------------------

def get_or_create_user(email: str) -> int:
    now = _iso(_utcnow())
    with _connect() as c:
        row = c.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if row:
            c.execute("UPDATE users SET last_seen_at = ? WHERE id = ?", (now, row["id"]))
            return row["id"]
        cur = c.execute(
            "INSERT INTO users(email, created_at, last_seen_at) VALUES (?, ?, ?)",
            (email, now, now),
        )
        return cur.lastrowid


def create_session(user_id: int, ip: str = "", user_agent: str = "") -> tuple[str, datetime]:
    token = secrets.token_urlsafe(48)
    now = _utcnow()
    expires = now + SESSION_DURATION
    with _connect() as c:
        c.execute(
            "INSERT INTO sessions(token, user_id, created_at, expires_at, ip, user_agent) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (token, user_id, _iso(now), _iso(expires), ip, user_agent),
        )
    return token, expires


def get_session_user(token: str) -> Optional[sqlite3.Row]:
    if not token:
        return None
    with _connect() as c:
        row = c.execute(
            """
            SELECT u.id, u.email, u.created_at, u.last_seen_at, s.expires_at
            FROM sessions s JOIN users u ON u.id = s.user_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()
        if not row:
            return None
        if _parse(row["expires_at"]) < _utcnow():
            c.execute("DELETE FROM sessions WHERE token = ?", (token,))
            return None
        c.execute(
            "UPDATE users SET last_seen_at = ? WHERE id = ?",
            (_iso(_utcnow()), row["id"]),
        )
        return row


def delete_session(token: str) -> None:
    if not token:
        return
    with _connect() as c:
        c.execute("DELETE FROM sessions WHERE token = ?", (token,))


def list_users(search: str = "", limit: int = 200) -> list[sqlite3.Row]:
    with _connect() as c:
        if search:
            like = f"%{search.lower()}%"
            rows = c.execute(
                "SELECT id, email, created_at, last_seen_at FROM users "
                "WHERE LOWER(email) LIKE ? ORDER BY created_at DESC LIMIT ?",
                (like, limit),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id, email, created_at, last_seen_at FROM users "
                "ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return rows


def delete_user(user_id: int) -> None:
    with _connect() as c:
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))


def stats() -> dict:
    with _connect() as c:
        users = c.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"]
        sessions_count = c.execute(
            "SELECT COUNT(*) AS n FROM sessions WHERE expires_at > ?",
            (_iso(_utcnow()),),
        ).fetchone()["n"]
        recent = c.execute(
            "SELECT COUNT(*) AS n FROM users WHERE last_seen_at > ?",
            (_iso(_utcnow() - timedelta(days=7)),),
        ).fetchone()["n"]
        return {
            "users": users,
            "active_sessions": sessions_count,
            "active_last_7d": recent,
        }


def cleanup_expired() -> None:
    """Best-effort purge of expired sessions."""
    now = _iso(_utcnow())
    with _connect() as c:
        c.execute("DELETE FROM sessions WHERE expires_at < ?", (now,))


_LAST_CLEANUP = 0.0


def _maybe_cleanup() -> None:
    global _LAST_CLEANUP
    if time.time() - _LAST_CLEANUP > 3600:
        try:
            cleanup_expired()
        except Exception:
            pass
        _LAST_CLEANUP = time.time()


# ---------------------------------------------------------------------------
# Flask integration
# ---------------------------------------------------------------------------

def load_current_user() -> None:
    """Flask before_request hook: populate g.current_user from session cookie."""
    _maybe_cleanup()
    g.current_user = None
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        row = get_session_user(token)
        if row:
            g.current_user = {"id": row["id"], "email": row["email"]}
    # Stable per-device key so anonymous visitors also keep their
    # bookmarks / notes / last position. Set elsewhere by ensure_device_key.
    g.device_key = request.cookies.get(DEVICE_COOKIE_NAME) or None


def ensure_device_key(response):
    """Attach a long-lived random device-key cookie if the visitor doesn't
    have one yet. Call this from an after_request hook."""
    if request.cookies.get(DEVICE_COOKIE_NAME):
        return response
    key = secrets.token_urlsafe(24)
    g.device_key = key
    response.set_cookie(
        DEVICE_COOKIE_NAME, key,
        max_age=int(DEVICE_DURATION.total_seconds()),
        httponly=True, secure=request.is_secure, samesite="Lax", path="/",
    )
    return response


def _owner_filter():
    """Returns (sql_clause, params) selecting rows owned by the current
    user (preferred) or the current device key. Falls back to a clause
    that matches nothing when no identity is present."""
    user = g.get("current_user") or {}
    if user.get("id"):
        return ("user_id = ?", (user["id"],))
    key = g.get("device_key")
    if key:
        return ("device_key = ?", (key,))
    return ("1 = 0", ())


def _owner_columns():
    """Returns ('user_id, device_key', (uid_or_None, key_or_None)) for
    INSERT statements."""
    user = g.get("current_user") or {}
    if user.get("id"):
        return ("user_id, device_key", (user["id"], None))
    return ("user_id, device_key", (None, g.get("device_key")))


def has_owner() -> bool:
    return bool((g.get("current_user") or {}).get("id") or g.get("device_key"))


# ---------------------------------------------------------------------------
# Reading state, bookmarks, notes, highlights
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return _iso(_utcnow())


def get_reading_state() -> Optional[dict]:
    where, params = _owner_filter()
    with _connect() as c:
        row = c.execute(
            f"SELECT book, chapter, verse, view, updated_at "
            f"FROM reading_state WHERE {where}", params,
        ).fetchone()
        return dict(row) if row else None


def save_reading_state(book: str, chapter: int, verse: Optional[int], view: Optional[str]) -> None:
    if not has_owner():
        return
    user = g.get("current_user") or {}
    uid = user.get("id")
    key = None if uid else g.get("device_key")
    now = _now_iso()
    with _connect() as c:
        if uid:
            existing = c.execute("SELECT id FROM reading_state WHERE user_id = ?", (uid,)).fetchone()
        else:
            existing = c.execute("SELECT id FROM reading_state WHERE device_key = ?", (key,)).fetchone()
        if existing:
            c.execute(
                "UPDATE reading_state SET book=?, chapter=?, verse=?, view=?, updated_at=? WHERE id=?",
                (book, chapter, verse, view, now, existing["id"]),
            )
        else:
            c.execute(
                "INSERT INTO reading_state(user_id, device_key, book, chapter, verse, view, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (uid, key, book, chapter, verse, view, now),
            )


def list_bookmarks() -> list[dict]:
    where, params = _owner_filter()
    with _connect() as c:
        rows = c.execute(
            f"SELECT id, book, chapter, verse, label, created_at "
            f"FROM bookmarks WHERE {where} ORDER BY created_at DESC", params,
        ).fetchall()
        return [dict(r) for r in rows]


def add_bookmark(book: str, chapter: int, verse: int, label: str = "") -> Optional[int]:
    if not has_owner():
        return None
    cols, vals = _owner_columns()
    with _connect() as c:
        cur = c.execute(
            f"INSERT INTO bookmarks({cols}, book, chapter, verse, label, created_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*vals, book, chapter, int(verse), label or None, _now_iso()),
        )
        return cur.lastrowid


def delete_bookmark(bookmark_id: int) -> bool:
    where, params = _owner_filter()
    with _connect() as c:
        cur = c.execute(
            f"DELETE FROM bookmarks WHERE id = ? AND {where}",
            (int(bookmark_id), *params),
        )
        return cur.rowcount > 0


def list_notes(book: Optional[str] = None, chapter: Optional[int] = None) -> list[dict]:
    where, params = _owner_filter()
    extra = ""
    extra_params: tuple = ()
    if book and chapter:
        extra = " AND book = ? AND chapter = ?"
        extra_params = (book, int(chapter))
    with _connect() as c:
        rows = c.execute(
            f"SELECT id, book, chapter, verse, body, created_at, updated_at "
            f"FROM notes WHERE {where}{extra} "
            f"ORDER BY book, chapter, verse",
            (*params, *extra_params),
        ).fetchall()
        return [dict(r) for r in rows]


def upsert_note(book: str, chapter: int, verse: int, body: str) -> Optional[int]:
    if not has_owner():
        return None
    body = (body or "").strip()
    where, params = _owner_filter()
    now = _now_iso()
    with _connect() as c:
        existing = c.execute(
            f"SELECT id FROM notes WHERE {where} AND book = ? AND chapter = ? AND verse = ?",
            (*params, book, int(chapter), int(verse)),
        ).fetchone()
        if existing:
            if not body:
                c.execute("DELETE FROM notes WHERE id = ?", (existing["id"],))
                return None
            c.execute(
                "UPDATE notes SET body = ?, updated_at = ? WHERE id = ?",
                (body, now, existing["id"]),
            )
            return existing["id"]
        if not body:
            return None
        cols, vals = _owner_columns()
        cur = c.execute(
            f"INSERT INTO notes({cols}, book, chapter, verse, body, created_at, updated_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (*vals, book, int(chapter), int(verse), body, now, now),
        )
        return cur.lastrowid


def delete_note(note_id: int) -> bool:
    where, params = _owner_filter()
    with _connect() as c:
        cur = c.execute(
            f"DELETE FROM notes WHERE id = ? AND {where}",
            (int(note_id), *params),
        )
        return cur.rowcount > 0


_VALID_HIGHLIGHT_COLORS = {"yellow", "green", "blue", "pink", "orange", "purple"}


def list_highlights(book: Optional[str] = None, chapter: Optional[int] = None) -> list[dict]:
    where, params = _owner_filter()
    extra = ""
    extra_params: tuple = ()
    if book and chapter:
        extra = " AND book = ? AND chapter = ?"
        extra_params = (book, int(chapter))
    with _connect() as c:
        rows = c.execute(
            f"SELECT id, book, chapter, verse, color, created_at "
            f"FROM highlights WHERE {where}{extra}",
            (*params, *extra_params),
        ).fetchall()
        return [dict(r) for r in rows]


def set_highlight(book: str, chapter: int, verse: int, color: str) -> Optional[int]:
    if not has_owner():
        return None
    color = (color or "").lower().strip()
    if color not in _VALID_HIGHLIGHT_COLORS:
        return None
    where, params = _owner_filter()
    with _connect() as c:
        existing = c.execute(
            f"SELECT id FROM highlights WHERE {where} AND book = ? AND chapter = ? AND verse = ?",
            (*params, book, int(chapter), int(verse)),
        ).fetchone()
        if existing:
            c.execute("UPDATE highlights SET color = ? WHERE id = ?", (color, existing["id"]))
            return existing["id"]
        cols, vals = _owner_columns()
        cur = c.execute(
            f"INSERT INTO highlights({cols}, book, chapter, verse, color, created_at) "
            f"VALUES (?, ?, ?, ?, ?, ?, ?)",
            (*vals, book, int(chapter), int(verse), color, _now_iso()),
        )
        return cur.lastrowid


def clear_highlight(book: str, chapter: int, verse: int) -> bool:
    where, params = _owner_filter()
    with _connect() as c:
        cur = c.execute(
            f"DELETE FROM highlights WHERE {where} AND book = ? AND chapter = ? AND verse = ?",
            (*params, book, int(chapter), int(verse)),
        )
        return cur.rowcount > 0


# ---------------------------------------------------------------------------
# Admin (separate credential-based auth, stored in env)
# ---------------------------------------------------------------------------

ADMIN_USER = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASS_HASH = os.environ.get("ADMIN_PASS_HASH", "")
ADMIN_SESSION_KEY = "admin_authenticated"


def verify_admin(username: str, password: str) -> bool:
    """Constant-time check against ADMIN_USER + werkzeug password hash."""
    from werkzeug.security import check_password_hash

    if not ADMIN_PASS_HASH:
        return False
    if not secrets.compare_digest(username or "", ADMIN_USER):
        return False
    try:
        return check_password_hash(ADMIN_PASS_HASH, password or "")
    except Exception:
        return False


def admin_required(view):
    from flask import redirect, url_for

    @wraps(view)
    def wrapper(*args, **kwargs):
        if not session.get(ADMIN_SESSION_KEY):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapper
