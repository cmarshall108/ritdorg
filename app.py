from flask import Flask, render_template, jsonify, request
import json
import os
import re
import logging
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import JSONFormatter

from translations import *
from bible_data import NT_BOOKS, NT_TRANSLATIONS
import bible_fetcher

logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Create YouTubeTranscriptApi instance
ytt_api = YouTubeTranscriptApi()

# On first startup, export hardcoded data from translations.py into JSON cache
# so the dynamic fetcher can serve Matthew/Mark instantly.
bible_fetcher.export_hardcoded_to_cache()

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
    key = f"{book}_{chapter}"
    
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

@app.route('/api/captions/<video_id>')
def get_video_captions(video_id):
    """Fetch captions/subtitles from a YouTube video for dynamic sync"""
    try:
        transcript_list = ytt_api.list(video_id)
        
        # Try to find a transcript
        transcript = None
        transcript_language = None
        
        # Priority 1: Try manually created English transcripts
        english_langs = ['en', 'en-US', 'en-GB']
        try:
            for lang in english_langs:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    transcript_language = lang
                    break
                except:
                    continue
        except:
            pass
        
        # Priority 2: Try auto-generated English
        if not transcript:
            try:
                for lang in english_langs:
                    try:
                        transcript = transcript_list.find_generated_transcript([lang])
                        transcript_language = lang
                        break
                    except:
                        continue
            except:
                pass
        
        # Priority 3: Try to translate any available transcript to English
        if not transcript:
            try:
                available = list(transcript_list)
                for t in available:
                    if t.is_translatable:
                        try:
                            transcript = t.translate('en')
                            transcript_language = 'en (translated from ' + t.language_code + ')'
                            break
                        except:
                            continue
            except:
                pass
        
        # Priority 4: Fall back to any available transcript
        if not transcript:
            try:
                available = list(transcript_list)
                if available:
                    transcript = available[0]
                    transcript_language = transcript.language_code
            except:
                pass
        
        if transcript:
            # Fetch the actual transcript data
            captions = transcript.fetch()
            
            # Format for our sync system
            formatted_captions = []
            for caption in captions:
                # New API uses object attributes instead of dict keys
                start = caption.start
                duration = caption.duration
                text = caption.text
                end = start + duration
                
                # Split text into words and calculate word timings
                words = text.split()
                word_timings = []
                if words:
                    word_duration = duration / len(words)
                    for i, word in enumerate(words):
                        word_start = start + (i * word_duration)
                        word_end = word_start + word_duration
                        word_timings.append({
                            "text": word,
                            "start": word_start,
                            "end": word_end
                        })
                
                formatted_captions.append({
                    "text": text,
                    "start": start,
                    "duration": duration,
                    "end": end,
                    "words": word_timings
                })
            
            return jsonify({
                "video_id": video_id,
                "language": transcript_language,
                "is_generated": transcript.is_generated,
                "captions": formatted_captions,
                "success": True
            })
        else:
            return jsonify({
                "video_id": video_id,
                "error": "No captions available for this video",
                "success": False
            })
            
    except Exception as e:
        return jsonify({
            "video_id": video_id,
            "error": str(e),
            "success": False
        })

@app.route('/api/captions/<video_id>/languages')
def get_caption_languages(video_id):
    """Get available caption languages for a video"""
    try:
        transcript_list = ytt_api.list(video_id)
        
        languages = []
        for transcript in transcript_list:
            languages.append({
                "code": transcript.language_code,
                "name": transcript.language,
                "is_generated": transcript.is_generated,
                "is_translatable": transcript.is_translatable
            })
        
        return jsonify({
            "video_id": video_id,
            "languages": languages,
            "success": True
        })
    except Exception as e:
        return jsonify({
            "video_id": video_id,
            "error": str(e),
            "success": False
        })

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

if __name__ == '__main__':
    app.run(debug=False, port=80, host='0.0.0.0')
