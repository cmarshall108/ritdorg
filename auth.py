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
SESSION_DURATION = timedelta(days=7)
DISMISS_DURATION = timedelta(days=30)

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
