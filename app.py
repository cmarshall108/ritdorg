from flask import (
    Flask, render_template, jsonify, request, Response,
    redirect, url_for, session, flash, g, make_response, abort,
    send_from_directory,
)
import glob
import json
import os
import logging

from translations import *
from bible_data import NT_BOOKS, ALL_BOOKS, NT_TRANSLATIONS
import bible_fetcher
import bible_xml
import lexicon
import auth
import video_transcode
import study

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
_DEFAULT_SECRET = "dev-secret-change-me"
app.secret_key = os.environ.get("SECRET_KEY", _DEFAULT_SECRET)
if app.secret_key == _DEFAULT_SECRET:
    logger.warning(
        "SECRET_KEY is using the insecure default. Set the SECRET_KEY "
        "environment variable before serving production traffic."
    )

# On first startup, export hardcoded data from translations.py into JSON cache
# so the dynamic fetcher can serve Matthew/Mark instantly.
bible_fetcher.export_hardcoded_to_cache()

# Initialize the auth database (users, sessions, newsletters).
auth.init_db()
# Add the study-tools tables (tags, outlines, playlists, etc.).
study.init_study_db()
# Initialize editable pages with defaults
auth.init_default_pages()
# If no ADMIN_PASS_HASH is provided in the environment, fall back to the
# documented default account so the panel is reachable on a fresh install.
auth.ensure_default_admin()


# ---------------------------------------------------------------------------
# Auth: load any logged-in user, but never gate access. Email is optional.
# ---------------------------------------------------------------------------

@app.before_request
def _load_user():
    auth.load_current_user()


@app.before_request
def _log_pageview():
    """Record a row in the analytics table for real reader page loads.

    Filtered down to GETs that aren't /static, /api/, /admin, /auth/, etc.
    Runs after _load_user so we can attach the logged-in user_id.
    """
    try:
        if not auth.should_log_request(request.path or "", request.method or "GET"):
            return
        # Background pruning of old rows so the table doesn't grow unbounded.
        auth._maybe_prune_pageviews()
        user = g.get("current_user") or {}
        ip = request.headers.get("X-Forwarded-For", request.remote_addr or "")
        # Only the first hop is useful; X-Forwarded-For can be a list.
        if "," in ip:
            ip = ip.split(",", 1)[0].strip()
        auth.log_pageview(
            path=request.path or "",
            referrer=request.referrer or "",
            user_agent=request.headers.get("User-Agent") or "",
            ip=ip[:64],
            visitor_key=request.cookies.get(auth.DEVICE_COOKIE_NAME),
            user_id=user.get("id"),
            country=request.headers.get("CF-IPCountry"),
        )
    except Exception:
        pass


@app.after_request
def _ensure_device_key(response):
    return auth.ensure_device_key(response)


# ---------------------------------------------------------------------------
# CORS for the native mobile app (Capacitor iOS / Android WKWebView).
# Origins seen in practice:
#   iOS      -> capacitor://localhost
#   Android  -> https://localhost  (also http://localhost when allowMixedContent)
#   Web dev  -> http://localhost[:port]  /  http://127.0.0.1[:port]
# We echo the Origin (can't use "*" with credentialed requests) and allow
# cookies so the existing session/device-cookie auth keeps working.
# ---------------------------------------------------------------------------

_ALLOWED_CORS_ORIGINS = {
    "capacitor://localhost",
    "ionic://localhost",
    "https://localhost",
    "http://localhost",
}


def _origin_is_allowed(origin: str) -> bool:
    if not origin:
        return False
    if origin in _ALLOWED_CORS_ORIGINS:
        return True
    # Local dev: http://localhost:PORT and http://127.0.0.1:PORT
    if origin.startswith(("http://localhost:", "http://127.0.0.1:")):
        return True
    return False


@app.after_request
def _add_cors_headers(response):
    origin = request.headers.get("Origin", "")
    if _origin_is_allowed(origin):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = (
            request.headers.get("Access-Control-Request-Headers")
            or "Content-Type, Authorization, X-Requested-With"
        )
        response.headers["Access-Control-Allow-Methods"] = (
            "GET, POST, PUT, PATCH, DELETE, OPTIONS"
        )
        response.headers["Access-Control-Max-Age"] = "86400"
    return response


@app.before_request
def _handle_cors_preflight():
    if request.method == "OPTIONS" and request.headers.get(
        "Access-Control-Request-Method"
    ):
        # Empty 204; the after_request hook above adds the CORS headers.
        return make_response("", 204)


@app.context_processor
def _inject_user():
    user = g.get("current_user")
    show_prompt = (
        user is None
        and not (request.path or "/").startswith("/admin")
    )
    return {
        "current_user": user,
        "show_email_prompt": show_prompt,
    }


@app.context_processor
def _inject_seo():
    """Expose a stable canonical URL (no query string) to templates.

    Templates pull `canonical_url` for <link rel="canonical"> + Open Graph
    tags via templates/_seo.html.
    """
    try:
        # Honor X-Forwarded-Proto/Host so the URL is correct behind a
        # reverse proxy (Cloudflare / nginx) rather than echoing http://.
        scheme = request.headers.get("X-Forwarded-Proto", request.scheme or "https")
        host = request.headers.get("X-Forwarded-Host") or request.host
        path = request.path or "/"
        canonical = f"{scheme}://{host}{path}"
    except Exception:
        canonical = "https://www.ritd.org/"
    return {"canonical_url": canonical}


def _available_translations():
    """All translation names: every XML file under bible_data/ plus
    legacy aliases (NIV/KJV/Hebrew/...) so existing UI/API keeps working.
    Legacy names come first, then the full XML catalogue alphabetically.
    """
    xml_names = bible_xml.list_translations()
    legacy = [
        n for n in NT_TRANSLATIONS
        if bible_xml.resolve_translation(n) is not None
        or n in BIBLE_TRANSLATIONS  # hard-coded fallback still serves it
    ]
    seen = set(legacy)
    extras = [n for n in xml_names if n not in seen]
    return legacy + extras

@app.route('/')
def index():
    books = list(ALL_BOOKS.keys())
    return render_template('index.html', books=books, translations=_available_translations())


@app.route('/favicon.ico')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'static', 'images'),
        'ritd-logo.png',
    )


# ---------------------------------------------------------------------------
# SEO: robots.txt + sitemap.xml so search engines (Google/Bing/DuckDuckGo)
# can crawl and rank the public pages.
# ---------------------------------------------------------------------------

# Public, indexable URL paths. Newsletter detail pages are added dynamically.
_PUBLIC_PAGE_PATHS = [
    '/',
    '/videos',
    '/services',
    '/qa',
    '/newsletter',
    '/founders',
    '/contact',
    '/hebrew-lessons',
    '/downloads',
    '/vision',
]


def _site_root() -> str:
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme or "https")
    host = request.headers.get("X-Forwarded-Host") or request.host
    return f"{scheme}://{host}"


@app.route('/robots.txt')
def robots_txt():
    root = _site_root()
    body = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin\n"
        "Disallow: /admin/\n"
        "Disallow: /api/\n"
        "Disallow: /logout\n"
        "Disallow: /static/videos/\n"
        "\n"
        f"Sitemap: {root}/sitemap.xml\n"
    )
    return Response(body, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    from xml.sax.saxutils import escape as _xe
    root = _site_root()
    urls = []
    for p in _PUBLIC_PAGE_PATHS:
        urls.append({
            'loc': f"{root}{p}",
            'changefreq': 'weekly' if p == '/' else 'monthly',
            'priority': '1.0' if p == '/' else '0.7',
        })
    # Newsletter detail pages.
    try:
        for n in auth.list_newsletters(status='published') or []:
            slug = (n.get('slug') or '').strip()
            if not slug:
                continue
            lastmod = n.get('published_at') or n.get('updated_at') or ''
            entry = {
                'loc': f"{root}/newsletter/{slug}",
                'changefreq': 'yearly',
                'priority': '0.6',
            }
            if lastmod:
                # Strip time component if present so the date is valid W3C.
                entry['lastmod'] = lastmod.split(' ', 1)[0].split('T', 1)[0]
            urls.append(entry)
    except Exception:
        pass

    parts = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        parts.append('  <url>')
        parts.append(f"    <loc>{_xe(u['loc'])}</loc>")
        if u.get('lastmod'):
            parts.append(f"    <lastmod>{_xe(u['lastmod'])}</lastmod>")
        parts.append(f"    <changefreq>{u['changefreq']}</changefreq>")
        parts.append(f"    <priority>{u['priority']}</priority>")
        parts.append('  </url>')
    parts.append('</urlset>\n')
    return Response('\n'.join(parts), mimetype='application/xml')

@app.route('/api/books')
def get_books():
    return jsonify(list(ALL_BOOKS.keys()))

@app.route('/api/translations')
def get_translations():
    return jsonify(_available_translations())

@app.route('/api/chapters/<book>')
def get_chapters(book):
    if book in ALL_BOOKS:
        return jsonify(list(range(1, ALL_BOOKS[book]['chapters'] + 1)))
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
    try:
        limit = min(max(int(request.args.get('limit', 100)), 1), 500)
    except (TypeError, ValueError):
        limit = 100

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

        for book_name, info in ALL_BOOKS.items():
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

@app.route('/api/verse-of-the-day')
def get_verse_of_the_day():
    """Get the verse of the day.
    
    Query params:
        date - ISO date (YYYY-MM-DD), or None for today UTC
        include_text - boolean, whether to fetch the actual verse text
    
    Returns:
        {
            book, chapter, verse, translation, computed_date,
            text (optional) - the actual verse text from the specified translation
        }
    """
    date_str = request.args.get('date')
    include_text = request.args.get('include_text', 'false').lower() in ('true', '1', 'yes')
    
    # Generate/fetch the verse of the day
    votd = auth.generate_verse_of_the_day(date_str)
    if not votd:
        return jsonify({'error': 'Failed to generate verse of the day'}), 500
    
    # Optionally fetch the text
    if include_text:
        verses = bible_fetcher.get_verses(
            votd['translation'], votd['book'], votd['chapter']
        )
        if verses:
            text = verses.get(str(votd['verse'])) or verses.get(votd['verse'])
            if text:
                votd['text'] = text
    
    return jsonify(votd)

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


# ---------------------------------------------------------------------------
# Strong's Hebrew & Greek lexicon
# ---------------------------------------------------------------------------

@app.route('/api/lexicon/<lang>/<strongs_id>')
def lexicon_entry(lang, strongs_id):
    """Return one Strong's entry by id (e.g. /api/lexicon/hebrew/H7225)."""
    lang = (lang or '').lower()
    if lang not in ('hebrew', 'greek'):
        return jsonify({"error": "lang must be 'hebrew' or 'greek'"}), 400
    entry = lexicon.get_entry(lang, strongs_id)
    if not entry:
        return jsonify({"error": "not found", "id": strongs_id, "lang": lang}), 404
    return jsonify({"lang": lang, "entry": entry})


@app.route('/api/lexicon/search')
def lexicon_search():
    """Search the Strong's lexicon by lemma, transliteration, or gloss.

    Query params:
        lang  - 'hebrew' or 'greek' (required)
        q     - search query (required)
        limit - max results (default 25, max 200)
    """
    lang = (request.args.get('lang') or '').lower()
    q = request.args.get('q', '').strip()
    if lang not in ('hebrew', 'greek'):
        return jsonify({"error": "lang must be 'hebrew' or 'greek'"}), 400
    if not q:
        return jsonify({"lang": lang, "query": q, "count": 0, "results": []})
    try:
        limit = max(1, min(200, int(request.args.get('limit', '25'))))
    except (TypeError, ValueError):
        limit = 25
    results = lexicon.search(lang, q, limit=limit)
    return jsonify({
        "lang": lang,
        "query": q,
        "count": len(results),
        "results": results,
        "loaded": lexicon.is_loaded(lang),
    })


@app.route('/api/analytics/activity', methods=['POST'])
def api_analytics_activity():
    """Receive lightweight interaction + active-time events from the browser."""
    payload = request.get_json(silent=True) or {}
    events = payload.get('events') if isinstance(payload, dict) else None
    if not isinstance(events, list):
        events = [payload] if isinstance(payload, dict) else []

    user = g.get('current_user') or {}
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or '')
    if ',' in ip:
        ip = ip.split(',', 1)[0].strip()
    ua = request.headers.get('User-Agent') or ''
    visitor_key = request.cookies.get(auth.DEVICE_COOKIE_NAME)

    accepted = 0
    for ev in events[:50]:
        if not isinstance(ev, dict):
            continue
        session_id = (ev.get('session_id') or '').strip()
        path = (ev.get('path') or request.path or '').strip()
        if not session_id or not path.startswith('/'):
            continue
        details = ev.get('details') if isinstance(ev.get('details'), dict) else None
        try:
            auth.log_activity_event(
                session_id=session_id,
                path=path,
                event_type=(ev.get('event_type') or '')[:48],
                event_name=(ev.get('event_name') or '')[:64],
                active_seconds=int(ev.get('active_seconds') or 0),
                scroll_depth=ev.get('scroll_depth'),
                details=details,
                user_agent=ua,
                ip=ip[:64],
                visitor_key=visitor_key,
                user_id=user.get('id'),
            )
            accepted += 1
        except Exception:
            continue

    return jsonify({'ok': True, 'accepted': accepted})

@app.route('/api/tts')
def tts_audio():
    """Server-side TTS. Returns MP3 audio for the given text in the
    requested language.

    Primary engine: Microsoft Edge neural voices (via the ``edge-tts``
    package). These sound dramatically more natural than the legacy
    Google Translate voices.

    Fallback: gTTS (Google Translate TTS) — used only if edge-tts errors
    or the package is missing.

    Query params:
      text  — sentence/verse to synthesize (required, max 1500 chars)
      lang  — BCP-47 language code (e.g. "en", "en-US", "hu", "he").
              Used to pick a default voice if ``voice`` is not given.
      voice — explicit edge voice short-name (e.g. "en-US-AriaNeural").
              Whitelist-validated to belong to a supported language.
      tld   — gTTS top-level domain accent, only used when falling back
              to gTTS or when voice='gtts'.
    """
    text = (request.args.get('text') or '').strip()
    lang_raw = (request.args.get('lang') or 'en').strip()
    lang = lang_raw.split('-')[0].lower()
    voice = (request.args.get('voice') or '').strip()
    tld = (request.args.get('tld') or 'com').strip().lower()
    ALLOWED_TLDS = {'com', 'co.uk', 'com.au', 'ca', 'co.in', 'ie', 'co.za'}
    if tld not in ALLOWED_TLDS:
        tld = 'com'

    if not text:
        abort(400, 'text required')

    # Sanitize control / bidi / cantillation marks before sending to any
    # engine. (Both edge-tts and gTTS handle nikud fine.)
    import re
    text = re.sub(r'[\u200B-\u200F\u202A-\u202E\uFEFF]', '', text)
    text = re.sub(r'[\u0591-\u05AF]', '', text)
    text = text.replace('\u05BE', '-')
    if len(text) > 1500:
        text = text[:1500]
    if not text.strip():
        abort(400, 'text empty after sanitization')

    # Resolve voice → engine + voice short-name.
    # Voices are listed in EDGE_VOICES (below). 'gtts' is a sentinel
    # meaning "use the legacy gTTS engine".
    engine = 'edge'
    if voice == 'gtts':
        engine = 'gtts'
        voice = ''
    elif voice and voice not in EDGE_VOICE_NAMES:
        # Unknown / spoofed voice — fall back to default for the language.
        voice = ''
    if engine == 'edge' and not voice:
        voice = DEFAULT_EDGE_VOICE.get(lang) or DEFAULT_EDGE_VOICE['en']

    if engine == 'edge':
        cached = study.tts_cache_lookup(text, lang, voice)
        if cached:
            resp = Response(cached, mimetype='audio/mpeg')
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            resp.headers['X-TTS-Cache'] = 'hit'
            return resp
        try:
            audio_bytes = _synthesize_edge(text, voice)
            study.tts_cache_store(text, lang, voice, audio_bytes)
            resp = Response(audio_bytes, mimetype='audio/mpeg')
            resp.headers['Cache-Control'] = 'public, max-age=86400'
            return resp
        except Exception as e:
            app.logger.warning(
                'edge-tts failed for voice=%s len=%d: %s — falling back to gTTS',
                voice, len(text), e,
            )
            engine = 'gtts'

    # gTTS fallback path.
    GTTS_LANG_ALIAS = {'he': 'iw', 'jv': 'jw'}
    glang = GTTS_LANG_ALIAS.get(lang, lang)
    try:
        from gtts import gTTS
        import io
        buf = io.BytesIO()
        gTTS(text=text, lang=glang, tld=tld).write_to_fp(buf)
        buf.seek(0)
        resp = Response(buf.getvalue(), mimetype='audio/mpeg')
        resp.headers['Cache-Control'] = 'public, max-age=86400'
        return resp
    except Exception as e:
        app.logger.warning('TTS failed for lang=%s len=%d: %s', lang, len(text), e)
        abort(503, f'TTS unavailable: {e}')


# --- Edge TTS voice catalog ----------------------------------------------
# Curated list of high-quality neural voices we expose in the UI. Trimmed
# from the full edge-tts catalog (~400 voices) to keep the picker usable.
EDGE_VOICES = {
    'en': [
        # (short-name, friendly label)
        ('en-US-AriaNeural',     'Aria — US, female (warm)'),
        ('en-US-JennyNeural',    'Jenny — US, female (friendly)'),
        ('en-US-GuyNeural',      'Guy — US, male'),
        ('en-US-DavisNeural',    'Davis — US, male (deep)'),
        ('en-US-AndrewNeural',   'Andrew — US, male (warm)'),
        ('en-US-EmmaNeural',     'Emma — US, female'),
        ('en-US-AvaNeural',      'Ava — US, female (expressive)'),
        ('en-US-BrianNeural',    'Brian — US, male'),
        ('en-GB-LibbyNeural',    'Libby — UK, female'),
        ('en-GB-RyanNeural',     'Ryan — UK, male'),
        ('en-GB-SoniaNeural',    'Sonia — UK, female'),
        ('en-AU-NatashaNeural',  'Natasha — Australian, female'),
        ('en-AU-WilliamNeural',  'William — Australian, male'),
        ('en-CA-ClaraNeural',    'Clara — Canadian, female'),
        ('en-IE-EmilyNeural',    'Emily — Irish, female'),
        ('en-IN-NeerjaNeural',   'Neerja — Indian, female'),
        ('en-ZA-LeahNeural',     'Leah — South African, female'),
    ],
    'hu': [
        ('hu-HU-NoemiNeural',    'Noémi — female'),
        ('hu-HU-TamasNeural',    'Tamás — male'),
    ],
    'he': [
        ('he-IL-HilaNeural',     'Hila — female'),
        ('he-IL-AvriNeural',     'Avri — male'),
    ],
}
EDGE_VOICE_NAMES = {v[0] for vs in EDGE_VOICES.values() for v in vs}
DEFAULT_EDGE_VOICE = {
    'en': 'en-US-AriaNeural',
    'hu': 'hu-HU-NoemiNeural',
    'he': 'he-IL-HilaNeural',
}


def _synthesize_edge(text: str, voice: str) -> bytes:
    """Synthesize ``text`` with edge-tts, returning MP3 bytes.

    edge-tts is async; we run it on a fresh event loop per request so it
    plays nicely with Flask's threaded WSGI server.
    """
    import asyncio
    import edge_tts

    async def _run():
        comm = edge_tts.Communicate(text, voice)
        chunks = bytearray()
        async for chunk in comm.stream():
            if chunk.get('type') == 'audio' and chunk.get('data'):
                chunks.extend(chunk['data'])
        return bytes(chunks)

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run())
    finally:
        loop.close()


@app.route('/api/tts/voices')
def tts_voices():
    """Expose the curated voice catalog to the client (settings dialog)."""
    out = {}
    for lang, voices in EDGE_VOICES.items():
        out[lang] = [{'id': v[0], 'label': v[1]} for v in voices]
    # Synthetic "use legacy Google Translate voice" option per language.
    for lang in out:
        out[lang].append({'id': 'gtts', 'label': '— Legacy Google voice —'})
    return jsonify(out)


# ----- Hebrew word study -----------------------------------------------------
# Curated dictionary file mapping fully-pointed Hebrew words to short English
# glosses. Loaded once at import time. Lookup strips Hebrew vowel points and
# cantillation marks (U+0591..U+05C7) when an exact match isn't found, so users
# can tap a word in any verse and still get a definition.

_HEB_DICT_PATH = os.path.join(app.static_folder, 'data', 'hebrew_dictionary.json')
_HEB_DICT = None
_HEB_DICT_NORM = None  # consonant-only key -> (original_key, gloss)


def _strip_hebrew_marks(s):
    # Remove cantillation/nikud and the maqaf join character so e.g.
    # "בְּרֵאשִׁית" and "ברישית" both reduce to "בראשית"-ish forms.
    return ''.join(c for c in (s or '') if not ('\u0591' <= c <= '\u05C7')).replace('\u05BE', ' ').strip()


def _load_hebrew_dict():
    global _HEB_DICT, _HEB_DICT_NORM
    if _HEB_DICT is not None:
        return _HEB_DICT, _HEB_DICT_NORM
    try:
        with open(_HEB_DICT_PATH, 'r', encoding='utf-8') as f:
            _HEB_DICT = json.load(f)
    except Exception as e:
        logger.warning("Could not load Hebrew dictionary: %s", e)
        _HEB_DICT = {}
    _HEB_DICT_NORM = {}
    for k, v in _HEB_DICT.items():
        nk = _strip_hebrew_marks(k)
        if nk and nk not in _HEB_DICT_NORM:
            _HEB_DICT_NORM[nk] = (k, v)
    return _HEB_DICT, _HEB_DICT_NORM


@app.route('/api/hebrew/define')
def hebrew_define():
    """Return a short English gloss for a Hebrew word.

    Query: ?word=<hebrew word, with or without nikud>
    Response: { word, gloss, matched, normalized } or 404.
    """
    word = (request.args.get('word') or '').strip()
    if not word:
        return jsonify({'error': 'word required'}), 400
    # Trim trailing punctuation/maqaf and surrounding whitespace.
    word = word.strip(' \t\n\r,.;:!?\u05BE\u00B7"\'()[]{}')
    direct, norm_map = _load_hebrew_dict()
    if word in direct:
        return jsonify({'word': word, 'gloss': direct[word], 'matched': word, 'source': 'exact'})
    n = _strip_hebrew_marks(word)
    if n and n in norm_map:
        matched, gloss = norm_map[n]
        return jsonify({'word': word, 'gloss': gloss, 'matched': matched, 'normalized': n, 'source': 'normalized'})
    return jsonify({'word': word, 'gloss': None, 'normalized': n, 'source': 'none'}), 404


@app.route('/api/hebrew/dictionary')
def hebrew_dictionary():
    """Return the full curated dictionary (for client-side caching)."""
    direct, _ = _load_hebrew_dict()
    return jsonify(direct)


# ---------------------------------------------------------------------------
# Word-occurrence counter (used by the per-word study popover for every
# language). For Hebrew we strip cantillation/nikud and split on maqaf;
# for other languages we lowercase and split on Unicode word boundaries.
# Each translation's full corpus is loaded lazily on first request and
# cached in process memory.
# ---------------------------------------------------------------------------

_TRANSLATION_CORPUS = {}    # translation_display -> list[(book, ch, v, raw_text, norm_text)]
_TRANSLATION_CORPUS_LOCK = None

# Filesystem-slug per translation. Mirrors the on-disk layout under
# static/data/bible/<slug>/<book_slug>/<chapter>.json.
TRANSLATION_DIR_SLUGS = {
    'NIV': 'niv',
    'NKJV': 'nkjv',
    'KJV': 'kjv',
    'ESV': 'esv',
    'NASB1995': 'nasb1995',
    'Hungarian': 'hungarian',
    'Hungarian-Revised': 'hungarian-revised',
    'Hebrew': 'hebrew',
    'Kenyah': 'kenyah',
}

# BCP-47-ish language code per translation (used to pick a TTS voice).
TRANSLATION_LANG = {
    'NIV': 'en', 'NKJV': 'en', 'KJV': 'en', 'ESV': 'en', 'NASB1995': 'en',
    'Hungarian': 'hu', 'Hungarian-Revised': 'hu',
    'Hebrew': 'he',
    'Kenyah': 'id',
}


def _normalize_word_for_lang(word, lang):
    """Return a canonical comparable form of ``word`` for the given language."""
    if not word:
        return ''
    if lang == 'he':
        return _strip_hebrew_marks(word).strip()
    # Generic case (English / Hungarian): lowercase + strip surrounding
    # punctuation. Hungarian needs casefold for ő/ű.
    import re
    cleaned = re.sub(r'^[\s\W_]+|[\s\W_]+$', '', word, flags=re.UNICODE)
    return cleaned.casefold()


def _tokenize_for_lang(text, lang):
    """Return a list of comparable tokens from ``text`` in ``lang``."""
    if not text:
        return []
    if lang == 'he':
        return _strip_hebrew_marks(text).split()
    # Word characters (Unicode-aware) — works for English and Hungarian.
    import re
    return [m.group(0).casefold() for m in re.finditer(r"[^\W_]+(?:'[^\W_]+)?", text, re.UNICODE)]


def _load_translation_corpus(translation):
    """Scan static/data/bible/<slug>/**/*.json once and return a flat list
    of (book_display, chapter, verse, raw_text, normalized_text) tuples.
    Skips entries whose value isn't a real verse (e.g. section headers,
    or non-Hebrew strings inside the Hebrew folder)."""
    global _TRANSLATION_CORPUS_LOCK
    cached = _TRANSLATION_CORPUS.get(translation)
    if cached is not None:
        return cached
    if _TRANSLATION_CORPUS_LOCK is None:
        import threading
        _TRANSLATION_CORPUS_LOCK = threading.Lock()
    with _TRANSLATION_CORPUS_LOCK:
        cached = _TRANSLATION_CORPUS.get(translation)
        if cached is not None:
            return cached
        slug = TRANSLATION_DIR_SLUGS.get(translation)
        if not slug:
            _TRANSLATION_CORPUS[translation] = []
            return []
        lang = TRANSLATION_LANG.get(translation, 'en')
        import re
        heb_re = re.compile(r'[\u0590-\u05FF]')
        slug_to_display = {b.lower().replace(' ', '_'): b for b in ALL_BOOKS.keys()}
        root = os.path.join(app.static_folder, 'data', 'bible', slug)
        corpus = []
        if os.path.isdir(root):
            for book_slug in os.listdir(root):
                book_dir = os.path.join(root, book_slug)
                if not os.path.isdir(book_dir):
                    continue
                display = slug_to_display.get(book_slug, book_slug.replace('_', ' ').title())
                for fname in os.listdir(book_dir):
                    if not fname.endswith('.json'):
                        continue
                    try:
                        chapter = int(fname.rsplit('.', 1)[0])
                    except ValueError:
                        continue
                    try:
                        with open(os.path.join(book_dir, fname), 'r', encoding='utf-8') as f:
                            verses = json.load(f)
                    except Exception:
                        continue
                    if not isinstance(verses, dict):
                        continue
                    for vk, vt in verses.items():
                        if not isinstance(vt, str) or not vt.strip():
                            continue
                        # For Hebrew, skip section-header entries that
                        # only contain English text.
                        if lang == 'he' and not heb_re.search(vt):
                            continue
                        try:
                            vnum = int(vk)
                        except (ValueError, TypeError):
                            continue
                        if lang == 'he':
                            norm = _strip_hebrew_marks(vt)
                        else:
                            norm = ' '.join(_tokenize_for_lang(vt, lang))
                        corpus.append((display, chapter, vnum, vt, norm))
        _TRANSLATION_CORPUS[translation] = corpus
        return corpus


def _load_hebrew_corpus():
    """Backwards-compatible wrapper used by the Hebrew-only endpoint."""
    return _load_translation_corpus('Hebrew')


@app.route('/api/hebrew/occurrences')
def hebrew_occurrences():
    """Count occurrences of a Hebrew word across the entire cached
    Hebrew corpus.

    Matches by consonant-only normalization (cantillation/nikud
    stripped, maqaf treated as word boundary), so a single query like
    בֶּן will match both pointed and unpointed forms anywhere in the
    canon.

    Query params:
      word   — Hebrew word (required, may include points/cantillation).
      limit  — maximum number of sample references to return (default 25).

    Returns:
      {
        word, normalized,
        count,                 // total tokens matched across the corpus
        verses_with_matches,   // distinct verses containing ≥1 match
        samples: [{book, chapter, verse, text, hits}]
      }
    """
    raw = (request.args.get('word') or '').strip()
    try:
        limit = max(1, min(200, int(request.args.get('limit') or 25)))
    except ValueError:
        limit = 25
    if not raw:
        return jsonify({'error': 'word required'}), 400
    target = _strip_hebrew_marks(raw).strip()
    if not target:
        return jsonify({'error': 'word has no Hebrew letters'}), 400

    corpus = _load_hebrew_corpus()
    total_hits = 0
    verses_with_matches = 0
    samples = []
    for (book, chapter, verse, text, norm_text) in corpus:
        # Token-level match on the normalized verse — split on any
        # whitespace (the normalizer already converted maqaf to space).
        tokens = norm_text.split()
        hits = sum(1 for t in tokens if t == target)
        if hits == 0:
            continue
        total_hits += hits
        verses_with_matches += 1
        if len(samples) < limit:
            samples.append({
                'book': book, 'chapter': chapter, 'verse': verse,
                'text': text, 'hits': hits,
            })
    return jsonify({
        'word': raw,
        'normalized': target,
        'count': total_hits,
        'verses_with_matches': verses_with_matches,
        'corpus_size': len(corpus),
        'samples': samples,
    })


@app.route('/api/words/occurrences')
def word_occurrences():
    """Count occurrences of a word in any cached translation.

    Query params:
      word         — the word to search (required).
      translation  — display name of the translation (default: NIV).
      limit        — max sample references to return (default 25).

    Matching is language-aware: Hebrew uses consonant-only normalization,
    other languages use Unicode-word casefolded comparison.
    """
    raw = (request.args.get('word') or '').strip()
    translation = (request.args.get('translation') or 'NIV').strip()
    try:
        limit = max(1, min(200, int(request.args.get('limit') or 25)))
    except ValueError:
        limit = 25
    if not raw:
        return jsonify({'error': 'word required'}), 400
    if translation not in TRANSLATION_DIR_SLUGS:
        return jsonify({'error': 'unknown translation'}), 400
    lang = TRANSLATION_LANG.get(translation, 'en')
    target = _normalize_word_for_lang(raw, lang)
    if not target:
        return jsonify({'error': 'word is empty after normalization'}), 400

    corpus = _load_translation_corpus(translation)
    total_hits = 0
    verses_with_matches = 0
    samples = []
    for (book, chapter, verse, text, norm_text) in corpus:
        tokens = norm_text.split() if lang == 'he' else norm_text.split(' ')
        hits = sum(1 for t in tokens if t == target)
        if hits == 0:
            continue
        total_hits += hits
        verses_with_matches += 1
        if len(samples) < limit:
            samples.append({
                'book': book, 'chapter': chapter, 'verse': verse,
                'text': text, 'hits': hits,
            })
    return jsonify({
        'word': raw,
        'normalized': target,
        'translation': translation,
        'lang': lang,
        'count': total_hits,
        'verses_with_matches': verses_with_matches,
        'corpus_size': len(corpus),
        'samples': samples,
    })


@app.route('/api/words/lang')
def word_lang_map():
    """Expose the translation→language map to the client."""
    return jsonify({
        'languages': TRANSLATION_LANG,
        'translations': sorted(TRANSLATION_DIR_SLUGS.keys()),
    })


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
    video_dir = os.path.join(app.static_folder, 'videos')
    video_files = []
    for ext in ('*.mp4', '*.mov', '*.webm'):
        video_files.extend(glob.glob(os.path.join(video_dir, ext)))
    video_files.sort(key=lambda f: os.path.getmtime(f), reverse=True)
    video_names = [os.path.basename(f) for f in video_files]
    return render_template('videos.html', videos=video_names)


@app.route('/static/videos/<path:filename>')
def serve_video(filename):
    """Serve uploaded videos with a browser-friendly MIME type.

    iPhone-recorded ``.mov`` files are H.264 + AAC inside a QuickTime
    container. Chrome and Firefox refuse to play files served as
    ``video/quicktime`` (the default for the ``.mov`` extension), but
    will happily decode the same bytes when the response is labeled as
    ``video/mp4``. ``send_from_directory`` returns a conditional
    response, so HTTP Range requests (needed for seeking and progressive
    download of large files) keep working.
    """
    video_dir = os.path.join(app.static_folder, 'videos')
    ext = os.path.splitext(filename)[1].lower()
    mimetype = {
        '.mp4':  'video/mp4',
        '.mov':  'video/mp4',
        '.m4v':  'video/mp4',
        '.webm': 'video/webm',
    }.get(ext, 'application/octet-stream')
    return send_from_directory(
        video_dir, filename,
        mimetype=mimetype,
        conditional=True,
    )

@app.route('/services')
def services():
    return render_template('services.html')

@app.route('/qa')
def qa():
    return render_template('qa.html')

@app.route('/newsletter')
def newsletter():
    items = auth.list_newsletters(status='published')
    return render_template('newsletter.html', newsletters=items)


@app.route('/newsletter/<slug>')
def newsletter_detail(slug):
    item = auth.get_newsletter_by_slug(slug, published_only=True)
    if not item:
        abort(404)
    return render_template('newsletter_detail.html', n=item)

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


@app.route('/vision')
def vision():
    return render_template('vision.html')

# ---------------------------------------------------------------------------
# Per-visitor reading state, bookmarks, notes, highlights
# Tied to either the logged-in user or a long-lived device-key cookie,
# so anonymous visitors also keep their data across sessions.
# ---------------------------------------------------------------------------

@app.route('/api/me/state', methods=['GET'])
def api_get_state():
    return jsonify(auth.get_reading_state() or {})


@app.route('/api/me/state', methods=['PUT', 'POST'])
def api_save_state():
    data = request.get_json(silent=True) or {}
    book = (data.get('book') or '').strip()
    chapter = data.get('chapter')
    if not book or not isinstance(chapter, int):
        return jsonify({'ok': False, 'error': 'book and chapter required'}), 400
    if book not in ALL_BOOKS or not (1 <= chapter <= ALL_BOOKS[book]['chapters']):
        return jsonify({'ok': False, 'error': 'unknown book/chapter'}), 400
    verse = data.get('verse')
    if verse is not None:
        try: verse = int(verse)
        except (TypeError, ValueError): verse = None
    view = data.get('view')
    if view not in (None, 'reader', 'parallel', 'video'):
        view = None
    auth.save_reading_state(book, chapter, verse, view)
    return jsonify({'ok': True})


@app.route('/api/me/bookmarks', methods=['GET'])
def api_list_bookmarks():
    return jsonify({'bookmarks': auth.list_bookmarks()})


@app.route('/api/me/bookmarks', methods=['POST'])
def api_add_bookmark():
    data = request.get_json(silent=True) or {}
    book = (data.get('book') or '').strip()
    try:
        chapter = int(data.get('chapter'))
        verse = int(data.get('verse'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'chapter/verse required'}), 400
    if book not in ALL_BOOKS:
        return jsonify({'ok': False, 'error': 'unknown book'}), 400
    label = (data.get('label') or '').strip()[:120]
    new_id = auth.add_bookmark(book, chapter, verse, label)
    if new_id is None:
        return jsonify({'ok': False, 'error': 'no owner'}), 400
    return jsonify({'ok': True, 'id': new_id})


@app.route('/api/me/bookmarks/<int:bookmark_id>', methods=['DELETE'])
def api_delete_bookmark(bookmark_id):
    return jsonify({'ok': auth.delete_bookmark(bookmark_id)})


@app.route('/api/me/notes', methods=['GET'])
def api_list_notes():
    book = request.args.get('book') or None
    chapter = request.args.get('chapter')
    chapter = int(chapter) if (chapter and chapter.isdigit()) else None
    return jsonify({'notes': auth.list_notes(book, chapter)})


@app.route('/api/me/notes', methods=['POST', 'PUT'])
def api_upsert_note():
    data = request.get_json(silent=True) or {}
    book = (data.get('book') or '').strip()
    try:
        chapter = int(data.get('chapter'))
        verse = int(data.get('verse'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'chapter/verse required'}), 400
    body = (data.get('body') or '').strip()[:5000]
    if book not in ALL_BOOKS:
        return jsonify({'ok': False, 'error': 'unknown book'}), 400
    note_id = auth.upsert_note(book, chapter, verse, body)
    return jsonify({'ok': True, 'id': note_id})


@app.route('/api/me/notes/<int:note_id>', methods=['DELETE'])
def api_delete_note(note_id):
    return jsonify({'ok': auth.delete_note(note_id)})


@app.route('/api/me/highlights', methods=['GET'])
def api_list_highlights():
    book = request.args.get('book') or None
    chapter = request.args.get('chapter')
    chapter = int(chapter) if (chapter and chapter.isdigit()) else None
    return jsonify({'highlights': auth.list_highlights(book, chapter)})


@app.route('/api/me/highlights', methods=['POST', 'PUT'])
def api_set_highlight():
    data = request.get_json(silent=True) or {}
    book = (data.get('book') or '').strip()
    try:
        chapter = int(data.get('chapter'))
        verse = int(data.get('verse'))
    except (TypeError, ValueError):
        return jsonify({'ok': False, 'error': 'chapter/verse required'}), 400
    color = (data.get('color') or '').strip().lower()
    if book not in ALL_BOOKS:
        return jsonify({'ok': False, 'error': 'unknown book'}), 400
    if not color:
        ok = auth.clear_highlight(book, chapter, verse)
        return jsonify({'ok': ok})
    new_id = auth.set_highlight(book, chapter, verse, color)
    if new_id is None:
        return jsonify({'ok': False, 'error': 'invalid color'}), 400
    return jsonify({'ok': True, 'id': new_id, 'color': color})


# ----- Pastor study tools: bulk export ---------------------------------------
# Markdown exports of the user's notes / bookmarks / a single chapter, suitable
# for sermon prep. Returned as text/markdown with a Content-Disposition so the
# browser offers a download dialog.

def _md_escape(s):
    """Escape characters that have meaning in Markdown."""
    return (s or '').replace('\\', '\\\\').replace('*', '\\*').replace('_', '\\_')


@app.route('/api/me/export/notes')
def api_export_all_notes():
    notes = auth.list_notes()
    lines = ["# My Bible study notes", ""]
    if not notes:
        lines.append("_No notes yet._")
    else:
        # Group by book/chapter for readability.
        by_loc = {}
        for n in notes:
            key = (n['book'], int(n['chapter']))
            by_loc.setdefault(key, []).append(n)
        for (book, chapter) in sorted(by_loc.keys(), key=lambda k: (list(ALL_BOOKS.keys()).index(k[0]) if k[0] in ALL_BOOKS else 999, k[1])):
            lines.append(f"## {book} {chapter}")
            lines.append("")
            for n in sorted(by_loc[(book, chapter)], key=lambda x: int(x['verse'])):
                stamp = n.get('updated_at') or n.get('created_at') or ''
                lines.append(f"### v{n['verse']}  \n_{stamp}_")
                lines.append("")
                lines.append((n.get('body') or '').strip())
                lines.append("")
    body = "\n".join(lines) + "\n"
    resp = make_response(body)
    resp.headers['Content-Type'] = 'text/markdown; charset=utf-8'
    resp.headers['Content-Disposition'] = 'attachment; filename="bible-notes.md"'
    return resp


@app.route('/api/me/export/bookmarks')
def api_export_all_bookmarks():
    bm = auth.list_bookmarks()
    lines = ["# My bookmarks", ""]
    if not bm:
        lines.append("_No bookmarks yet._")
    else:
        for b in bm:
            label = b.get('label') or ''
            ref = f"{b['book']} {b['chapter']}:{b['verse']}"
            stamp = b.get('created_at') or ''
            if label:
                lines.append(f"- **{ref}** — {_md_escape(label)}  _{stamp}_")
            else:
                lines.append(f"- **{ref}**  _{stamp}_")
    body = "\n".join(lines) + "\n"
    resp = make_response(body)
    resp.headers['Content-Type'] = 'text/markdown; charset=utf-8'
    resp.headers['Content-Disposition'] = 'attachment; filename="bible-bookmarks.md"'
    return resp


@app.route('/api/me/export/chapter/<book>/<int:chapter>')
def api_export_chapter(book, chapter):
    """Markdown export of a single chapter: the verse text from a chosen
    translation, with the user's notes interleaved verse-by-verse. Useful
    as a sermon-prep starter."""
    if book not in ALL_BOOKS:
        return jsonify({'error': 'unknown book'}), 404
    translation = (request.args.get('translation') or 'NIV').strip()
    verses = bible_fetcher.get_verses(translation, book, chapter) or {}
    actual_translation = translation
    if not verses:
        # Fall back to NIV so the export is never empty.
        verses = bible_fetcher.get_verses('NIV', book, chapter) or {}
        actual_translation = 'NIV'

    notes = {int(n['verse']): n for n in auth.list_notes(book, chapter)}
    lines = [
        f"# {book} {chapter} ({actual_translation})",
        "",
    ]
    # Verse keys may come back as either int or str depending on cache origin.
    norm_verses = {int(k): v for k, v in verses.items()}
    for vnum in sorted(norm_verses.keys()):
        text = norm_verses[vnum] or ''
        lines.append(f"**{vnum}.** {text}")
        lines.append("")
        if vnum in notes:
            body = (notes[vnum].get('body') or '').strip()
            if body:
                # Render the user's note as a blockquote so it's visually
                # distinct from the verse text.
                for ln in body.splitlines():
                    lines.append(f"> {ln}")
                lines.append("")
    body = "\n".join(lines) + "\n"
    resp = make_response(body)
    resp.headers['Content-Type'] = 'text/markdown; charset=utf-8'
    safe = f"{book.lower().replace(' ', '_')}-{chapter}.md"
    resp.headers['Content-Disposition'] = f'attachment; filename="{safe}"'
    return resp


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


@app.route("/admin/analytics")
@auth.admin_required
def admin_analytics():
    try:
        days = int(request.args.get("days", 30))
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))
    data = auth.analytics_summary(days=days)
    return render_template("admin/analytics.html", data=data, days=days)


@app.route("/admin/analytics/session/<session_id>")
@auth.admin_required
def admin_analytics_session(session_id: str):
    detail = auth.analytics_session_detail(session_id)
    if not detail:
        flash("Session not found or expired.", "error")
        return redirect(url_for("admin_analytics"))
    return render_template("admin/analytics_session.html", detail=detail)


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


# ---------------------------------------------------------------------------
# Admin: newsletters
# ---------------------------------------------------------------------------

@app.route("/admin/newsletters")
@auth.admin_required
def admin_newsletters():
    items = auth.list_newsletters()
    return render_template("admin/newsletters.html", newsletters=items)


@app.route("/admin/newsletters/new", methods=["GET", "POST"])
@auth.admin_required
def admin_newsletter_new():
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        subtitle = (request.form.get("subtitle") or "").strip()
        body_md = request.form.get("body_md") or ""
        body_html = request.form.get("body_html") or ""
        action = request.form.get("action") or "save"
        publish = action == "publish"
        nid = auth.create_newsletter(
            title or "Untitled", subtitle, body_md, body_html, publish=publish,
        )
        flash(("Published." if publish else "Draft saved."), "info")
        return redirect(url_for("admin_newsletter_edit", newsletter_id=nid))
    return render_template("admin/newsletter_edit.html", newsletter=None)


@app.route("/admin/newsletters/<int:newsletter_id>", methods=["GET", "POST"])
@auth.admin_required
def admin_newsletter_edit(newsletter_id: int):
    item = auth.get_newsletter(newsletter_id)
    if not item:
        abort(404)
    if request.method == "POST":
        action = request.form.get("action") or "save"
        title = (request.form.get("title") or "").strip()
        subtitle = (request.form.get("subtitle") or "").strip()
        body_md = request.form.get("body_md") or ""
        body_html = request.form.get("body_html") or ""
        new_status = None
        if action == "publish":
            new_status = "published"
        elif action == "unpublish":
            new_status = "draft"
        auth.update_newsletter(
            newsletter_id,
            title=title, subtitle=subtitle,
            body_md=body_md, body_html=body_html,
            status=new_status,
        )
        if action == "publish":
            flash("Newsletter published.", "info")
        elif action == "unpublish":
            flash("Reverted to draft.", "info")
        else:
            flash("Saved.", "info")
        return redirect(url_for("admin_newsletter_edit", newsletter_id=newsletter_id))
    return render_template("admin/newsletter_edit.html", newsletter=item)


@app.route("/admin/newsletters/<int:newsletter_id>/delete", methods=["POST"])
@auth.admin_required
def admin_newsletter_delete(newsletter_id: int):
    auth.delete_newsletter(newsletter_id)
    flash("Newsletter deleted.", "info")
    return redirect(url_for("admin_newsletters"))


# ---------------------------------------------------------------------------
# Admin: videos (upload, rename, delete)
# ---------------------------------------------------------------------------

import re as _re
import unicodedata

ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm"}
MAX_VIDEO_BYTES = 1024 * 1024 * 1024          # 1 GiB upload cap
app.config["MAX_CONTENT_LENGTH"] = MAX_VIDEO_BYTES


def _safe_video_name(name: str) -> str:
    """Normalize a user-supplied filename so it stays inside the videos
    directory. Strips path separators, collapses whitespace, and keeps
    only conservative ASCII characters + the original extension."""
    name = unicodedata.normalize("NFKD", name or "")
    name = name.encode("ascii", "ignore").decode("ascii")
    name = os.path.basename(name).strip()
    if not name:
        return ""
    stem, ext = os.path.splitext(name)
    ext = ext.lower()
    if ext not in ALLOWED_VIDEO_EXTS:
        return ""
    stem = _re.sub(r"[^A-Za-z0-9._-]+", "_", stem).strip("._-")
    if not stem:
        stem = "video"
    return f"{stem[:100]}{ext}"


def _video_dir() -> str:
    d = os.path.join(app.static_folder, "videos")
    os.makedirs(d, exist_ok=True)
    return d


@app.route("/admin/videos")
@auth.admin_required
def admin_videos():
    d = _video_dir()
    statuses = video_transcode.all_statuses()
    files = []
    for entry in os.scandir(d):
        if not entry.is_file():
            continue
        ext = os.path.splitext(entry.name)[1].lower()
        if ext not in ALLOWED_VIDEO_EXTS:
            continue
        st = entry.stat()
        files.append({
            "name": entry.name,
            "size_mb": round(st.st_size / (1024 * 1024), 1),
            "mtime": st.st_mtime,
            "transcode_status": statuses.get(entry.name),
        })
    files.sort(key=lambda f: f["mtime"], reverse=True)
    return render_template(
        "admin/videos.html",
        videos=files,
        max_mb=MAX_VIDEO_BYTES // (1024 * 1024),
        ffmpeg_available=video_transcode.have_ffmpeg(),
    )


@app.route("/admin/videos/status")
@auth.admin_required
def admin_video_status():
    """Lightweight JSON endpoint the Videos page polls so the
    'Transcoding…' badge updates without a full reload."""
    return jsonify(video_transcode.all_statuses())


@app.route("/admin/videos/upload", methods=["POST"])
@auth.admin_required
def admin_video_upload():
    f = request.files.get("video")
    if not f or not f.filename:
        flash("No file selected.", "error")
        return redirect(url_for("admin_videos"))
    safe = _safe_video_name(f.filename)
    if not safe:
        flash("Unsupported file type. Allowed: mp4, mov, m4v, webm.", "error")
        return redirect(url_for("admin_videos"))
    target = os.path.join(_video_dir(), safe)
    # Avoid silently overwriting an existing upload.
    if os.path.exists(target):
        stem, ext = os.path.splitext(safe)
        i = 2
        while os.path.exists(os.path.join(_video_dir(), f"{stem}_{i}{ext}")):
            i += 1
        target = os.path.join(_video_dir(), f"{stem}_{i}{ext}")
    f.save(target)
    # Auto-convert HEVC / .mov / .m4v / .webm uploads to a browser-friendly
    # H.264 MP4 in the background. The original file stays in place until
    # the transcode finishes, then gets archived under static/videos/originals/.
    video_transcode.maybe_transcode_async(target, _video_dir())
    flash(f"Uploaded {os.path.basename(target)}.", "info")
    return redirect(url_for("admin_videos"))


@app.route("/admin/videos/<path:name>/delete", methods=["POST"])
@auth.admin_required
def admin_video_delete(name: str):
    safe = _safe_video_name(name)
    if not safe:
        abort(400)
    path = os.path.join(_video_dir(), safe)
    if os.path.isfile(path):
        try:
            os.remove(path)
            flash(f"Deleted {safe}.", "info")
        except OSError as e:
            flash(f"Delete failed: {e}", "error")
    return redirect(url_for("admin_videos"))


@app.route("/admin/videos/<path:name>/rename", methods=["POST"])
@auth.admin_required
def admin_video_rename(name: str):
    safe = _safe_video_name(name)
    new_raw = (request.form.get("new_name") or "").strip()
    # Preserve the original extension if the user only typed a stem.
    if new_raw and "." not in new_raw:
        new_raw += os.path.splitext(safe)[1]
    new_safe = _safe_video_name(new_raw)
    if not safe or not new_safe:
        flash("Invalid filename.", "error")
        return redirect(url_for("admin_videos"))
    src = os.path.join(_video_dir(), safe)
    dst = os.path.join(_video_dir(), new_safe)
    if not os.path.isfile(src):
        abort(404)
    if os.path.exists(dst) and os.path.abspath(src) != os.path.abspath(dst):
        flash("A file with that name already exists.", "error")
        return redirect(url_for("admin_videos"))
    os.rename(src, dst)
    flash(f"Renamed to {new_safe}.", "info")
    return redirect(url_for("admin_videos"))


# ---------------------------------------------------------------------------
# Admin: editable pages
# ---------------------------------------------------------------------------

@app.route("/admin/pages")
@auth.admin_required
def admin_pages():
    """List all editable pages"""
    pages = auth.list_pages()
    return render_template("admin/pages.html", pages=pages)


@app.route("/admin/pages/<slug>", methods=["GET", "POST"])
@auth.admin_required
def admin_page_edit(slug: str):
    """Edit a page"""
    page = auth.get_page_content(slug)
    if not page:
        abort(404)
    
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        body_html = request.form.get("body_html") or ""
        user_id = g.get("current_user", {}).get("id")
        
        if not title:
            flash("Title is required.", "error")
        else:
            success = auth.set_page_content(slug, title, body_html, user_id=user_id)
            if success:
                flash("Page saved.", "info")
            else:
                flash("Save failed.", "error")
        return redirect(url_for("admin_page_edit", slug=slug))
    
    return render_template("admin/page_edit.html", page=page)


@app.route("/admin/pages/new", methods=["GET", "POST"])
@auth.admin_required
def admin_page_new():
    """Create a new page"""
    if request.method == "POST":
        title = (request.form.get("title") or "").strip()
        slug = (request.form.get("slug") or "").strip().lower()
        slug = re.sub(r'[^a-z0-9-]', '', slug).strip('-')
        body_html = request.form.get("body_html") or ""
        user_id = g.get("current_user", {}).get("id")
        
        if not title or not slug:
            flash("Title and slug are required.", "error")
            return render_template("admin/page_edit.html", page=None, new_page=True)
        
        # Check if slug already exists
        existing = auth.get_page_content(slug)
        if existing:
            flash("A page with that slug already exists.", "error")
            return render_template("admin/page_edit.html", page=None, new_page=True)
        
        success = auth.set_page_content(slug, title, body_html, user_id=user_id)
        if success:
            flash("Page created.", "info")
            return redirect(url_for("admin_page_edit", slug=slug))
        else:
            flash("Failed to create page.", "error")
    
    return render_template("admin/page_edit.html", page=None, new_page=True)


@app.route("/admin/pages/<slug>/delete", methods=["POST"])
@auth.admin_required
def admin_page_delete(slug: str):
    """Delete a page"""
    if auth.delete_page(slug):
        flash("Page deleted.", "info")
    else:
        flash("Failed to delete page.", "error")
    return redirect(url_for("admin_pages"))


# Register the study-tools blueprint (cross-translation concordance,
# tags, outlines, playlists, reading plans, notebooks, exports, etc.).
app.register_blueprint(study.study_bp, url_prefix='/api')


if __name__ == '__main__':
    app.run(debug=False, port=80, host='0.0.0.0')
