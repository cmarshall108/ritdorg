from flask import (
    Flask, render_template, jsonify, request,
    redirect, url_for, session, flash, g, make_response,
)
import json
import os
import logging

from translations import *
from bible_data import NT_BOOKS, NT_TRANSLATIONS
import bible_fetcher
import auth

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

# On first startup, export hardcoded data from translations.py into JSON cache
# so the dynamic fetcher can serve Matthew/Mark instantly.
bible_fetcher.export_hardcoded_to_cache()

# Initialize the auth database (users, sessions).
auth.init_db()


# ---------------------------------------------------------------------------
# Auth: load any logged-in user, but never gate access. Email is optional.
# ---------------------------------------------------------------------------

@app.before_request
def _load_user():
    auth.load_current_user()


@app.context_processor
def _inject_user():
    user = g.get("current_user")
    show_prompt = (
        user is None
        and not request.cookies.get(auth.DISMISS_COOKIE_NAME)
        and not (request.path or "/").startswith("/admin")
    )
    return {
        "current_user": user,
        "show_email_prompt": show_prompt,
    }

@app.route('/')
def index():
    books = list(NT_BOOKS.keys())
    return render_template('index.html', books=books, translations=NT_TRANSLATIONS)

@app.route('/api/books')
def get_books():
    return jsonify(list(NT_BOOKS.keys()))

@app.route('/api/translations')
def get_translations():
    return jsonify(NT_TRANSLATIONS)

@app.route('/api/chapters/<book>')
def get_chapters(book):
    if book in NT_BOOKS:
        return jsonify(list(range(1, NT_BOOKS[book]['chapters'] + 1)))
    return jsonify([])

@app.route('/api/verses/<book>/<int:chapter>')
def get_verses(book, chapter):
    translation = request.args.get('translation', 'NIV')

    # 1. Try dynamic fetcher (checks cache, then fetches externally)
    verses = bible_fetcher.get_verses(translation, book, chapter)
    if verses:
        return jsonify({"verses": verses, "translation": translation, "fallback": False})

    # 2. Fall back to hardcoded data in translations.py
    bible = BIBLE_TRANSLATIONS.get(translation)
    if bible and book in bible and chapter in bible[book]:
        return jsonify({"verses": bible[book][chapter], "translation": translation, "fallback": False})

    # 3. Fall back to NIV (dynamic then hardcoded)
    niv = bible_fetcher.get_verses('NIV', book, chapter)
    if niv:
        return jsonify({"verses": niv, "translation": "NIV", "fallback": True})
    if book in BIBLE_NIV and chapter in BIBLE_NIV[book]:
        return jsonify({"verses": BIBLE_NIV[book][chapter], "translation": "NIV", "fallback": True})

    return jsonify({"verses": {}, "translation": translation, "fallback": False})

@app.route('/api/verses/parallel/<book>/<int:chapter>')
def get_parallel_verses(book, chapter):
    """Get verses in two translations side by side"""
    trans1 = request.args.get('translation1', 'NIV')
    trans2 = request.args.get('translation2', 'Hebrew')

    def _resolve(translation):
        """Try dynamic fetch → hardcoded → NIV fallback."""
        verses = bible_fetcher.get_verses(translation, book, chapter)
        if verses:
            return verses, translation, False
        bible = BIBLE_TRANSLATIONS.get(translation, {})
        if book in bible and chapter in bible[book]:
            return bible[book][chapter], translation, False
        # Fallback to NIV
        niv = bible_fetcher.get_verses('NIV', book, chapter)
        if niv:
            return niv, 'NIV', True
        if book in BIBLE_NIV and chapter in BIBLE_NIV[book]:
            return BIBLE_NIV[book][chapter], 'NIV', True
        return {}, translation, False

    verses1, actual1, fallback1 = _resolve(trans1)
    verses2, actual2, fallback2 = _resolve(trans2)

    return jsonify({
        "translation1": {"name": trans1, "actual": actual1, "verses": verses1, "fallback": fallback1},
        "translation2": {"name": trans2, "actual": actual2, "verses": verses2, "fallback": fallback2}
    })

@app.route('/api/search')
def search_bible():
    """
    Full-text search across cached Bible translations.

    Query params:
        q            – search term (required, min 2 chars)
        translation  – comma-separated list, or 'all' (default: all)
        limit        – max results to return (default: 100)
    """
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify({"error": "Query must be at least 2 characters", "results": []})

    translations_param = request.args.get('translation', 'all')
    limit = min(int(request.args.get('limit', 100)), 500)

    # Determine which translations to search
    if translations_param == 'all':
        search_translations = list(bible_fetcher.TRANSLATION_SOURCES.keys())
    else:
        search_translations = [t.strip() for t in translations_param.split(',')
                               if t.strip() in bible_fetcher.TRANSLATION_SOURCES]
        if not search_translations:
            search_translations = list(bible_fetcher.TRANSLATION_SOURCES.keys())

    results = []
    query_lower = query.lower()
    # For Hebrew searches, match the raw query (no lowercasing)
    is_hebrew_query = any('\u0590' <= ch <= '\u05FF' for ch in query)

    for translation in search_translations:
        trans_dir = os.path.join(bible_fetcher.CACHE_DIR, translation.lower())
        if not os.path.isdir(trans_dir):
            continue

        for book_name, info in NT_BOOKS.items():
            slug = info["slug"]
            book_dir = os.path.join(trans_dir, slug)
            if not os.path.isdir(book_dir):
                continue

            for ch in range(1, info["chapters"] + 1):
                chapter_file = os.path.join(book_dir, f"{ch}.json")
                if not os.path.exists(chapter_file):
                    continue
                try:
                    with open(chapter_file, "r", encoding="utf-8") as fh:
                        verses = json.load(fh)
                except Exception:
                    continue

                for verse_num, verse_text in verses.items():
                    if is_hebrew_query:
                        match = query in verse_text
                    else:
                        match = query_lower in verse_text.lower()

                    if match:
                        # Build a snippet with context around the match
                        if is_hebrew_query:
                            idx = verse_text.find(query)
                        else:
                            idx = verse_text.lower().find(query_lower)
                        start = max(0, idx - 40)
                        end = min(len(verse_text), idx + len(query) + 40)
                        snippet = ('…' if start > 0 else '') + verse_text[start:end] + ('…' if end < len(verse_text) else '')

                        results.append({
                            "translation": translation,
                            "book": book_name,
                            "chapter": ch,
                            "verse": int(verse_num),
                            "text": verse_text,
                            "snippet": snippet,
                        })

                        if len(results) >= limit:
                            return jsonify({
                                "query": query,
                                "count": len(results),
                                "truncated": True,
                                "results": results,
                            })

    return jsonify({
        "query": query,
        "count": len(results),
        "truncated": False,
        "results": results,
    })

@app.route('/api/sync/<book>/<int:chapter>')
def get_sync_data(book, chapter):
    """Get video sync data for a chapter, supporting playlists"""
    # Normalize: spaces to underscores so "1 Corinthians" -> "1_Corinthians_1"
    key = f"{book.replace(' ', '_')}_{chapter}"
    
    # Check if we have specific sync data for this chapter
    if key in VIDEO_SYNC_DATA:
        return jsonify(VIDEO_SYNC_DATA[key])
    
    # If no specific data, try to provide playlist-based data
    if book in RITDORG_PLAYLISTS:
        return jsonify({
            "video_id": None,
            "playlist_id": RITDORG_PLAYLISTS[book],
            "playlist_index": chapter - 1,  # Chapters are 1-indexed, playlist is 0-indexed
            "channel": "RITDorg",
            "title": f"{book} Chapter {chapter} - Bible Reading",
            "timestamps": []  # No word-level sync, but video will still play
        })
    
    return jsonify({"video_id": None, "playlist_id": None, "timestamps": [], "channel": "RITDorg"})

@app.route('/api/playlists')
def get_playlists():
    """Get all RITDorg playlists"""
    return jsonify(RITDORG_PLAYLISTS)

@app.route('/api/playlists/<book>')
def get_playlist_for_book(book):
    """Get the RITDorg playlist for a specific book"""
    if book in RITDORG_PLAYLISTS:
        return jsonify({
            "book": book,
            "playlist_id": RITDORG_PLAYLISTS[book],
            "playlist_url": f"https://www.youtube.com/playlist?list={RITDORG_PLAYLISTS[book]}"
        })
    return jsonify({"error": f"No playlist found for {book}"}), 404

@app.route('/videos')
def videos():
    import glob
    video_dir = os.path.join(app.static_folder, 'videos')
    video_files = []
    for ext in ('*.mp4', '*.mov', '*.webm'):
        video_files.extend(glob.glob(os.path.join(video_dir, ext)))
    video_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    video_names = [os.path.basename(f) for f in video_files]
    return render_template('videos.html', videos=video_names)

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/qa')
def qa():
    return render_template('qa.html')

@app.route('/newsletter')
def newsletter():
    return render_template('newsletter.html')

@app.route('/founders')
def founders():
    return render_template('founders.html')

@app.route('/contact')
def contact():
    return render_template('contact.html')

@app.route('/hebrew-lessons')
def hebrew_lessons():
    return render_template('hebrew-lessons.html')

@app.route('/downloads')
def downloads():
    return render_template('downloads.html')

# ---------------------------------------------------------------------------
# Optional email capture (encouraged, not required)
# ---------------------------------------------------------------------------

@app.route("/auth/save-email", methods=["POST"])
def save_email():
    """Save a visitor's email and create a 7-day session cookie.

    Accepts JSON ({"email": "..."}) or form-encoded.
    Returns JSON for fetch() callers; redirects for plain-form submissions.
    """
    data = request.get_json(silent=True) or request.form
    email = auth.normalize_email((data.get("email") or "").strip())

    wants_json = (
        request.is_json
        or request.headers.get("X-Requested-With") == "fetch"
        or "application/json" in (request.headers.get("Accept") or "")
    )

    if not email:
        if wants_json:
            return jsonify({"ok": False, "error": "Please enter a valid email."}), 400
        flash("Please enter a valid email.", "error")
        return redirect(request.referrer or url_for("index"))

    user_id = auth.get_or_create_user(email)
    session_token, expires = auth.create_session(
        user_id,
        ip=request.headers.get("X-Forwarded-For", request.remote_addr or ""),
        user_agent=(request.headers.get("User-Agent") or "")[:255],
    )

    if wants_json:
        resp = make_response(jsonify({"ok": True, "email": email}))
    else:
        resp = make_response(redirect(request.referrer or url_for("index")))
    resp.set_cookie(
        auth.SESSION_COOKIE_NAME,
        session_token,
        expires=expires,
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        path="/",
    )
    return resp


@app.route("/auth/dismiss-email-prompt", methods=["POST"])
def dismiss_email_prompt():
    """Set a cookie so the email prompt isn't shown again for a while."""
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie(
        auth.DISMISS_COOKIE_NAME,
        "1",
        max_age=int(auth.DISMISS_DURATION.total_seconds()),
        httponly=False,  # so JS can also see it
        secure=request.is_secure,
        samesite="Lax",
        path="/",
    )
    return resp


@app.route("/logout", methods=["GET", "POST"])
def logout():
    token = request.cookies.get(auth.SESSION_COOKIE_NAME)
    auth.delete_session(token)
    resp = make_response(redirect(url_for("index")))
    resp.delete_cookie(auth.SESSION_COOKIE_NAME, path="/")
    return resp


# ---------------------------------------------------------------------------
# Admin panel (separate username + password auth, env-configured)
# ---------------------------------------------------------------------------

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    next_url = request.args.get("next") or request.form.get("next") or url_for("admin_dashboard")
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if auth.verify_admin(username, password):
            session[auth.ADMIN_SESSION_KEY] = True
            session.permanent = False
            target = next_url if next_url.startswith("/") and not next_url.startswith("//") else url_for("admin_dashboard")
            return redirect(target)
        error = "Invalid username or password."
    return render_template("admin/login.html", error=error, next_url=next_url)


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    session.pop(auth.ADMIN_SESSION_KEY, None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
@auth.admin_required
def admin_dashboard():
    return render_template(
        "admin/dashboard.html",
        stats=auth.stats(),
    )


@app.route("/admin/users")
@auth.admin_required
def admin_users():
    q = request.args.get("q", "").strip()
    users = auth.list_users(search=q)
    return render_template("admin/users.html", users=users, q=q)


@app.route("/admin/users/<int:user_id>/delete", methods=["POST"])
@auth.admin_required
def admin_delete_user(user_id: int):
    auth.delete_user(user_id)
    flash("User deleted.", "info")
    return redirect(url_for("admin_users"))


if __name__ == '__main__':
    app.run(debug=False, port=80, host='0.0.0.0')
