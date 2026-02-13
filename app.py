from flask import Flask, render_template, jsonify, request
import json
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import JSONFormatter

from translations import *

app = Flask(__name__)

# Create YouTubeTranscriptApi instance
ytt_api = YouTubeTranscriptApi()

@app.route('/')
def index():
    books = [b for b in BIBLE_DATA.keys() if b not in EXCLUDED_BOOKS]
    return render_template('index.html', books=books, translations=TRANSLATIONS)

@app.route('/api/books')
def get_books():
    return jsonify([b for b in BIBLE_DATA.keys() if b not in EXCLUDED_BOOKS])

@app.route('/api/translations')
def get_translations():
    return jsonify(TRANSLATIONS)

@app.route('/api/chapters/<book>')
def get_chapters(book):
    if book in BIBLE_DATA:
        return jsonify(list(BIBLE_DATA[book].keys()))
    return jsonify([])

@app.route('/api/verses/<book>/<int:chapter>')
def get_verses(book, chapter):
    translation = request.args.get('translation', 'NIV')
    bible = BIBLE_TRANSLATIONS.get(translation, BIBLE_NIV)
    
    if book in bible and chapter in bible[book]:
        verses = bible[book][chapter]
        return jsonify({"verses": verses, "translation": translation, "fallback": False})
    
    return jsonify({"verses": {}, "translation": translation, "fallback": False})

@app.route('/api/verses/parallel/<book>/<int:chapter>')
def get_parallel_verses(book, chapter):
    """Get verses in two translations side by side"""
    trans1 = request.args.get('translation1', 'NIV')
    trans2 = request.args.get('translation2', 'HEBREW')
    
    bible1 = BIBLE_TRANSLATIONS.get(trans1, BIBLE_NIV)
    bible2 = BIBLE_TRANSLATIONS.get(trans2, BIBLE_HEBREW)
    
    verses1 = {}
    verses2 = {}
    fallback1 = False
    fallback2 = False
    actual_trans1 = trans1
    actual_trans2 = trans2
    
    if book in bible1 and chapter in bible1[book]:
        verses1 = bible1[book][chapter]
    elif book in BIBLE_NIV and chapter in BIBLE_NIV[book]:
        verses1 = BIBLE_NIV[book][chapter]
        fallback1 = True
        actual_trans1 = "NIV"
        
    if book in bible2 and chapter in bible2[book]:
        verses2 = bible2[book][chapter]
    elif book in BIBLE_HEBREW and chapter in BIBLE_HEBREW[book]:
        verses2 = BIBLE_HEBREW[book][chapter]
        fallback2 = True
        actual_trans2 = "HEBREW"
    
    return jsonify({
        "translation1": {"name": trans1, "actual": actual_trans1, "verses": verses1, "fallback": fallback1},
        "translation2": {"name": trans2, "actual": actual_trans2, "verses": verses2, "fallback": fallback2}
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

if __name__ == '__main__':
    app.run(debug=False, port=8000, host='0.0.0.0')
