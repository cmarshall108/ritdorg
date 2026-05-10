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

            -- Admin-authored newsletters. body_md is the raw markdown the
            -- editor saves; body_html is the rendered HTML (produced by the
            -- editor at save time so we don't depend on a python markdown
            -- package). status is 'draft' or 'published'.
            CREATE TABLE IF NOT EXISTS newsletters (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                slug          TEXT UNIQUE NOT NULL,
                title         TEXT NOT NULL,
                subtitle      TEXT,
                body_md       TEXT NOT NULL DEFAULT '',
                body_html     TEXT NOT NULL DEFAULT '',
                status        TEXT NOT NULL DEFAULT 'draft',
                created_at    TEXT NOT NULL,
                updated_at    TEXT NOT NULL,
                published_at  TEXT
            );
            CREATE INDEX IF NOT EXISTS newsletters_status_idx
                ON newsletters(status, published_at DESC);

            -- Page-view log used by the admin Analytics dashboard. One row
            -- per HTTP GET to a non-static, non-API URL. ``visitor_key`` is
            -- the long-lived ritd_device cookie, which lets us count unique
            -- visitors without storing PII. ``country`` is best-effort,
            -- populated from CF-IPCountry when available.
            CREATE TABLE IF NOT EXISTS pageviews (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          TEXT NOT NULL,
                path        TEXT NOT NULL,
                referrer    TEXT,
                user_agent  TEXT,
                ip          TEXT,
                visitor_key TEXT,
                user_id     INTEGER REFERENCES users(id) ON DELETE SET NULL,
                country     TEXT,
                device      TEXT,
                browser     TEXT
            );
            CREATE INDEX IF NOT EXISTS pageviews_ts_idx     ON pageviews(ts);
            CREATE INDEX IF NOT EXISTS pageviews_path_idx   ON pageviews(path);
            CREATE INDEX IF NOT EXISTS pageviews_visitor_idx ON pageviews(visitor_key);
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


def ensure_default_admin() -> None:
    """If no ADMIN_PASS_HASH is configured via env, fall back to a default
    administrator account so the panel is reachable on a fresh install.

    Default credentials: ``admin`` / ``RhemaWeb@1234``.

    These are intended only as a first-login convenience — operators should
    change them by setting ``ADMIN_USER`` / ``ADMIN_PASS_HASH`` in the
    environment. We log a warning whenever the defaults are in use.
    """
    global ADMIN_PASS_HASH, ADMIN_USER
    if ADMIN_PASS_HASH:
        return
    from werkzeug.security import generate_password_hash
    ADMIN_USER = ADMIN_USER or "admin"
    # Use pbkdf2 explicitly — werkzeug's default ('scrypt') depends on
    # hashlib.scrypt which isn't available on every Python build.
    ADMIN_PASS_HASH = generate_password_hash(
        "RhemaWeb@1234", method="pbkdf2:sha256",
    )
    import logging
    logging.getLogger(__name__).warning(
        "Using DEFAULT admin credentials (admin / RhemaWeb@1234). "
        "Set ADMIN_USER and ADMIN_PASS_HASH in the environment for production."
    )


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


# ---------------------------------------------------------------------------
# Newsletters (admin-authored content)
# ---------------------------------------------------------------------------

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    base = _SLUG_RE.sub("-", (text or "").lower()).strip("-")
    return base[:80] or "untitled"


def _unique_slug(base: str, existing_id: Optional[int] = None) -> str:
    base = slugify(base)
    candidate = base
    n = 2
    with _connect() as c:
        while True:
            row = c.execute(
                "SELECT id FROM newsletters WHERE slug = ?", (candidate,),
            ).fetchone()
            if not row or (existing_id is not None and row["id"] == existing_id):
                return candidate
            candidate = f"{base}-{n}"
            n += 1


def list_newsletters(status: Optional[str] = None) -> list[dict]:
    """Return newsletters newest first.

    ``status`` may be 'draft', 'published', or None for all.
    """
    with _connect() as c:
        if status:
            rows = c.execute(
                "SELECT id, slug, title, subtitle, status, created_at, "
                "updated_at, published_at FROM newsletters "
                "WHERE status = ? "
                "ORDER BY COALESCE(published_at, updated_at) DESC",
                (status,),
            ).fetchall()
        else:
            rows = c.execute(
                "SELECT id, slug, title, subtitle, status, created_at, "
                "updated_at, published_at FROM newsletters "
                "ORDER BY COALESCE(published_at, updated_at) DESC",
            ).fetchall()
        return [dict(r) for r in rows]


def get_newsletter(newsletter_id: int) -> Optional[dict]:
    with _connect() as c:
        row = c.execute(
            "SELECT * FROM newsletters WHERE id = ?", (int(newsletter_id),),
        ).fetchone()
        return dict(row) if row else None


def get_newsletter_by_slug(slug: str, *, published_only: bool = True) -> Optional[dict]:
    with _connect() as c:
        if published_only:
            row = c.execute(
                "SELECT * FROM newsletters WHERE slug = ? AND status = 'published'",
                (slug,),
            ).fetchone()
        else:
            row = c.execute(
                "SELECT * FROM newsletters WHERE slug = ?", (slug,),
            ).fetchone()
        return dict(row) if row else None


def create_newsletter(
    title: str, subtitle: str, body_md: str, body_html: str, *,
    publish: bool = False,
) -> int:
    title = (title or "Untitled").strip() or "Untitled"
    slug = _unique_slug(title)
    now = _now_iso()
    published_at = now if publish else None
    status = "published" if publish else "draft"
    with _connect() as c:
        cur = c.execute(
            "INSERT INTO newsletters(slug, title, subtitle, body_md, body_html, "
            "status, created_at, updated_at, published_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, title, (subtitle or "").strip() or None,
             body_md or "", body_html or "",
             status, now, now, published_at),
        )
        return cur.lastrowid


def update_newsletter(
    newsletter_id: int, *,
    title: Optional[str] = None,
    subtitle: Optional[str] = None,
    body_md: Optional[str] = None,
    body_html: Optional[str] = None,
    status: Optional[str] = None,
) -> bool:
    fields, params = [], []
    if title is not None:
        title = title.strip() or "Untitled"
        fields.append("title = ?"); params.append(title)
        # Re-slug from the new title so URLs stay readable.
        new_slug = _unique_slug(title, existing_id=newsletter_id)
        fields.append("slug = ?"); params.append(new_slug)
    if subtitle is not None:
        fields.append("subtitle = ?")
        params.append(subtitle.strip() or None)
    if body_md is not None:
        fields.append("body_md = ?"); params.append(body_md)
    if body_html is not None:
        fields.append("body_html = ?"); params.append(body_html)
    if status in ("draft", "published"):
        fields.append("status = ?"); params.append(status)
        if status == "published":
            fields.append("published_at = COALESCE(published_at, ?)")
            params.append(_now_iso())
    if not fields:
        return False
    fields.append("updated_at = ?"); params.append(_now_iso())
    params.append(int(newsletter_id))
    with _connect() as c:
        cur = c.execute(
            f"UPDATE newsletters SET {', '.join(fields)} WHERE id = ?",
            params,
        )
        return cur.rowcount > 0


def delete_newsletter(newsletter_id: int) -> bool:
    with _connect() as c:
        cur = c.execute(
            "DELETE FROM newsletters WHERE id = ?", (int(newsletter_id),),
        )
        return cur.rowcount > 0



# ---------------------------------------------------------------------------
# Analytics: lightweight first-party page-view logging.
# Recorded by Flask before_request and queried by the admin dashboard.
# No PII is stored — only the device cookie, IP, UA, and parsed device /
# browser. Old rows are pruned by retention policy below.
# ---------------------------------------------------------------------------

ANALYTICS_RETENTION_DAYS = int(os.environ.get("ANALYTICS_RETENTION_DAYS", "365"))

# Paths the analytics logger ignores. Anything starting with /static or
# /api/, plus the admin panel itself and ad-hoc auth endpoints, is skipped
# so the table stays focused on real reader page views.
_ANALYTICS_IGNORE_PREFIXES = (
    "/static/", "/api/", "/admin", "/auth/", "/logout", "/favicon",
)


def _ua_summary(ua: str) -> tuple[str, str]:
    """Best-effort device + browser from a User-Agent string.

    No external dependency — we just look for a few well-known tokens.
    Returns (device, browser); either may be 'Other'.
    """
    if not ua:
        return ("Other", "Other")
    s = ua.lower()
    # Device class
    if "ipad" in s:
        device = "Tablet"
    elif "iphone" in s or "android" in s and "mobile" in s:
        device = "Mobile"
    elif "android" in s:
        device = "Tablet"
    elif "windows" in s or "macintosh" in s or "linux" in s or "x11" in s:
        device = "Desktop"
    elif "bot" in s or "spider" in s or "crawler" in s:
        device = "Bot"
    else:
        device = "Other"
    # Browser
    if "edg/" in s:
        browser = "Edge"
    elif "chrome/" in s and "chromium" not in s:
        browser = "Chrome"
    elif "firefox/" in s:
        browser = "Firefox"
    elif "safari/" in s:
        browser = "Safari"
    elif "opera" in s or "opr/" in s:
        browser = "Opera"
    elif "bot" in s or "spider" in s or "crawler" in s:
        browser = "Bot"
    else:
        browser = "Other"
    return (device, browser)


def should_log_request(path: str, method: str) -> bool:
    if method != "GET":
        return False
    if not path:
        return False
    for p in _ANALYTICS_IGNORE_PREFIXES:
        if path.startswith(p):
            return False
    return True


def log_pageview(
    *, path: str, referrer: str = "", user_agent: str = "",
    ip: str = "", visitor_key: Optional[str] = None,
    user_id: Optional[int] = None, country: Optional[str] = None,
) -> None:
    device, browser = _ua_summary(user_agent or "")
    try:
        with _connect() as c:
            c.execute(
                "INSERT INTO pageviews(ts, path, referrer, user_agent, ip, "
                "visitor_key, user_id, country, device, browser) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    _now_iso(), path[:300], (referrer or "")[:500],
                    (user_agent or "")[:500], ip or "",
                    visitor_key, user_id, country,
                    device, browser,
                ),
            )
    except Exception:
        # Never let analytics break a real request.
        import logging as _l
        _l.getLogger(__name__).exception("pageview log failed")


_LAST_ANALYTICS_PRUNE = 0.0


def _maybe_prune_pageviews() -> None:
    global _LAST_ANALYTICS_PRUNE
    if time.time() - _LAST_ANALYTICS_PRUNE < 6 * 3600:
        return
    _LAST_ANALYTICS_PRUNE = time.time()
    cutoff = _iso(_utcnow() - timedelta(days=ANALYTICS_RETENTION_DAYS))
    try:
        with _connect() as c:
            c.execute("DELETE FROM pageviews WHERE ts < ?", (cutoff,))
    except Exception:
        pass


def analytics_summary(days: int = 30) -> dict:
    """Aggregate stats covering the last ``days`` days for the admin dashboard.

    Returns a dict with totals, top paths/referrers/countries/devices/browsers,
    a per-day timeseries, and the most recent pageviews list.
    """
    days = max(1, min(int(days or 30), 365))
    cutoff = _iso(_utcnow() - timedelta(days=days))
    today_cutoff = _iso(_utcnow() - timedelta(hours=24))
    yest_start = _iso(_utcnow() - timedelta(hours=48))

    with _connect() as c:
        def one(sql, params=()):
            row = c.execute(sql, params).fetchone()
            return row[0] if row else 0

        totals = {
            "views_window":      one("SELECT COUNT(*) FROM pageviews WHERE ts >= ?", (cutoff,)),
            "visitors_window":   one("SELECT COUNT(DISTINCT COALESCE(visitor_key, ip)) "
                                     "FROM pageviews WHERE ts >= ?", (cutoff,)),
            "views_24h":         one("SELECT COUNT(*) FROM pageviews WHERE ts >= ?", (today_cutoff,)),
            "visitors_24h":      one("SELECT COUNT(DISTINCT COALESCE(visitor_key, ip)) "
                                     "FROM pageviews WHERE ts >= ?", (today_cutoff,)),
            "views_prev_24h":    one("SELECT COUNT(*) FROM pageviews "
                                     "WHERE ts >= ? AND ts < ?", (yest_start, today_cutoff)),
            "all_time_views":    one("SELECT COUNT(*) FROM pageviews"),
            "all_time_visitors": one("SELECT COUNT(DISTINCT COALESCE(visitor_key, ip)) FROM pageviews"),
        }

        def rows(sql, params=()):
            return [dict(r) for r in c.execute(sql, params).fetchall()]

        # Timeseries — one row per day for the window.
        series = rows(
            "SELECT substr(ts, 1, 10) AS day, "
            "       COUNT(*) AS views, "
            "       COUNT(DISTINCT COALESCE(visitor_key, ip)) AS visitors "
            "FROM pageviews WHERE ts >= ? "
            "GROUP BY day ORDER BY day",
            (cutoff,),
        )
        # Fill in missing days so the chart is contiguous.
        from datetime import date
        by_day = {r["day"]: r for r in series}
        full = []
        today = _utcnow().date()
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            key = d.isoformat()
            r = by_day.get(key)
            full.append({"day": key, "views": (r or {}).get("views", 0),
                         "visitors": (r or {}).get("visitors", 0)})

        top_paths = rows(
            "SELECT path, COUNT(*) AS views, "
            "       COUNT(DISTINCT COALESCE(visitor_key, ip)) AS visitors "
            "FROM pageviews WHERE ts >= ? "
            "GROUP BY path ORDER BY views DESC LIMIT 20",
            (cutoff,),
        )
        top_referrers = rows(
            "SELECT referrer, COUNT(*) AS views FROM pageviews "
            "WHERE ts >= ? AND referrer != '' AND referrer IS NOT NULL "
            "GROUP BY referrer ORDER BY views DESC LIMIT 15",
            (cutoff,),
        )
        top_countries = rows(
            "SELECT COALESCE(country, '—') AS country, COUNT(*) AS views, "
            "       COUNT(DISTINCT COALESCE(visitor_key, ip)) AS visitors "
            "FROM pageviews WHERE ts >= ? "
            "GROUP BY country ORDER BY views DESC LIMIT 15",
            (cutoff,),
        )
        devices = rows(
            "SELECT COALESCE(device, 'Other') AS label, COUNT(*) AS n "
            "FROM pageviews WHERE ts >= ? GROUP BY label ORDER BY n DESC",
            (cutoff,),
        )
        browsers = rows(
            "SELECT COALESCE(browser, 'Other') AS label, COUNT(*) AS n "
            "FROM pageviews WHERE ts >= ? GROUP BY label ORDER BY n DESC",
            (cutoff,),
        )
        recent = rows(
            "SELECT ts, path, referrer, country, device, browser, ip "
            "FROM pageviews ORDER BY id DESC LIMIT 50"
        )
        # Hourly heatmap (UTC hour-of-day x day-of-week, last `days`).
        heat = rows(
            "SELECT CAST(strftime('%w', ts) AS INTEGER) AS dow, "
            "       CAST(strftime('%H', ts) AS INTEGER) AS hour, "
            "       COUNT(*) AS n "
            "FROM pageviews WHERE ts >= ? GROUP BY dow, hour",
            (cutoff,),
        )

    return {
        "days":          days,
        "totals":        totals,
        "timeseries":    full,
        "top_paths":     top_paths,
        "top_referrers": top_referrers,
        "top_countries": top_countries,
        "devices":       devices,
        "browsers":      browsers,
        "recent":        recent,
        "heatmap":       heat,
    }
