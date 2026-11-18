#!/usr/bin/env python3
"""Core Bible API tests (verses, search, tts, hebrew, lexicon, playlists, votd, etc).

Run with:
    PYTHONPATH=. python -m unittest tests.tests_core_api
or
    PYTHONPATH=. python tests/tests_core_api.py
"""
import os
import json
import asyncio
import tempfile
import shutil
import threading
import time
import unittest
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

# Must set AUTH_DB_PATH *before* importing any ritdorg.* so the module-level
# default in auth.py picks up our isolated temp DB.
TEST_TMP = tempfile.mkdtemp(prefix="ritdorg-test-")
TEST_DB = os.path.join(TEST_TMP, "auth.db")
os.environ["AUTH_DB_PATH"] = TEST_DB

# Now safe to import the app (bootstrap will set package context for relatives).
import ritdorg.app as appmod  # noqa: E402
from ritdorg.app import app  # noqa: E402

# Force the just-set AUTH_DB_PATH into the already-imported (or cached) auth
# module and re-initialize tables. This makes multi-test-module discover runs
# each get their own isolated DB even though 'import ritdorg.app' is a no-op
# on subsequent test modules in the same process.
import ritdorg.auth as _auth  # noqa: E402
import ritdorg.study as _study  # noqa: E402
_auth.AUTH_DB_PATH = os.environ["AUTH_DB_PATH"]
_auth.init_db()
_study.init_study_db()


def _seed_minimal_corpus(static_root: Path) -> None:
    """Create a tiny NIV cache so /api/search and concordance can be exercised."""
    cache_dir = static_root / "data" / "bible" / "niv" / "Genesis"
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "1": "In the beginning God created the heaven and the earth.",
        "2": "And the earth was without form, and void; and darkness was upon the face of the deep.",
        "3": "And God said, Let there be light: and there was light.",
        "4": "And God saw the light, that it was good: and God divided the light from the darkness.",
    }
    (cache_dir / "1.json").write_text(json.dumps(data), encoding="utf-8")

    # Also a tiny bit for another book to test cross-book search if wanted.
    exo = static_root / "data" / "bible" / "niv" / "Exodus"
    exo.mkdir(parents=True, exist_ok=True)
    (exo / "1.json").write_text(json.dumps({"1": "Now these are the names of the children of Israel..."}), encoding="utf-8")


def _cleanup_seed(static_root: Path) -> None:
    for p in [
        static_root / "data" / "bible" / "niv" / "Genesis" / "1.json",
        static_root / "data" / "bible" / "niv" / "Exodus" / "1.json",
    ]:
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass


class CoreAPITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static_root = Path(appmod.app.static_folder)
        _seed_minimal_corpus(cls.static_root)
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        _cleanup_seed(cls.static_root)
        try:
            shutil.rmtree(TEST_TMP, ignore_errors=True)
        except Exception:
            pass

    def test_healthz_endpoint(self):
        r = self.client.get("/healthz")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertTrue(data.get("ok"))
        self.assertEqual(data.get("db"), "ok")
        r2 = self.client.get("/api/health")
        self.assertEqual(r2.status_code, 200)

    def test_books_endpoint(self):
        r = self.client.get("/api/books")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)
        self.assertIn("Genesis", data)

    def test_translations_endpoint(self):
        r = self.client.get("/api/translations")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)
        self.assertGreater(len(data), 0)

    def test_chapters_endpoint(self):
        r = self.client.get("/api/chapters/Genesis")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsInstance(data, list)
        self.assertIn(1, data)
        self.assertGreaterEqual(len(data), 50)

    def test_verses_endpoint(self):
        r = self.client.get("/api/verses/Genesis/1?translation=NIV")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("verses", data)
        self.assertIn("translation", data)
        self.assertIn("1", data["verses"])  # at least some text

    def test_parallel_endpoint(self):
        r = self.client.get("/api/verses/parallel/Genesis/1?translation1=NIV&translation2=KJV")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("translation1", data)
        self.assertIn("translation2", data)

    def test_search_endpoint(self):
        # Uses the seeded corpus
        r = self.client.get("/api/search?q=beginning&translation=NIV&limit=5")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("results", data)
        self.assertGreaterEqual(data.get("count", 0), 1)

    def test_verse_of_the_day(self):
        r = self.client.get("/api/verse-of-the-day?include_text=1")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("book", data)
        self.assertIn("chapter", data)
        self.assertIn("verse", data)

    def test_playlists_endpoint(self):
        r = self.client.get("/api/playlists")
        self.assertEqual(r.status_code, 200)
        # Empty dict is valid (we added the missing const)
        data = r.get_json()
        self.assertIsInstance(data, dict)

    def test_sync_endpoint(self):
        r = self.client.get("/api/sync/Genesis/1")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("playlist_id", data)

    def test_tts_endpoint_basic(self):
        # Should not 500 even if no audio engine; returns mp3 or json error
        r = self.client.get("/api/tts?text=hello&lang=en")
        # Either audio or a json error body; accept 200 or 4xx/5xx but not crash
        self.assertIn(r.status_code, (200, 400, 500, 503))
        if r.content_type and "audio" in r.content_type:
            self.assertGreater(len(r.data), 100)

    def test_tts_voices(self):
        r = self.client.get("/api/tts/voices")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        # Shape may be list or dict depending on implementation; just ensure non-empty response
        self.assertTrue(data)

    def test_hebrew_define(self):
        r = self.client.get("/api/hebrew/define?word=%D7%91%D7%A8%D7%90%D7%A9%D7%99%D7%AA")
        self.assertIn(r.status_code, (200, 404))
        if r.status_code == 200:
            data = r.get_json()
            self.assertIsInstance(data, dict)

    def test_hebrew_dictionary(self):
        r = self.client.get("/api/hebrew/dictionary")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        # May be {} or {"words": ...} depending on load; accept either as long as 200
        self.assertIsInstance(data, dict)

    def test_lexicon_endpoint(self):
        # Strong's may or may not be populated; route should not 5xx
        r = self.client.get("/api/lexicon/en/H7225")
        self.assertIn(r.status_code, (200, 400, 404))

    def test_analytics_activity(self):
        r = self.client.post("/api/analytics/activity", json={"path": "/test", "ms": 12})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json().get("ok"), True)

    def test_tts_generation_guard_prevents_stale_callbacks(self):
        js_path = Path(appmod.app.static_folder) / "js" / "app.js"
        self.assertTrue(js_path.exists(), msg=f"Missing JS app: {js_path}")
        js_text = js_path.read_text(encoding="utf-8")
        self.assertIn("this._ttsGen = (this._ttsGen || 0) + 1;", js_text)
        self.assertIn("this.speakViaServer(item, myGen);", js_text)
        self.assertIn("if (myGen !== this._ttsGen) return;", js_text)


class TTSVoiceSelectionTestCase(unittest.TestCase):
    def test_concurrent_identical_requests_share_one_synthesis(self):
        started = threading.Event()
        release = threading.Event()
        waiting = threading.Event()

        class NotifyingFuture(Future):
            def result(self, timeout=None):
                waiting.set()
                return super().result(timeout)

        def synthesize(text, voice):
            started.set()
            self.assertTrue(release.wait(5))
            return b"shared-mp3"

        with (
            tempfile.TemporaryDirectory() as cache,
            patch("ritdorg.study._TTS_CACHE_DIR", cache),
            patch("ritdorg.study.Future", NotifyingFuture, create=True),
            patch("ritdorg.app._synthesize_edge", side_effect=synthesize) as upstream,
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            first = pool.submit(lambda: app.test_client().get("/api/tts?text=shared&lang=en"))
            self.assertTrue(started.wait(5))
            second = pool.submit(lambda: app.test_client().get("/api/tts?text=shared&lang=en"))
            try:
                self.assertTrue(waiting.wait(5))
            finally:
                release.set()
            self.assertEqual(first.result(timeout=5).data, b"shared-mp3")
            self.assertEqual(second.result(timeout=5).data, b"shared-mp3")
            self.assertEqual(upstream.call_count, 1)

    def test_google_audio_is_cached_per_accent(self):
        with (
            tempfile.TemporaryDirectory() as cache,
            patch("ritdorg.study._TTS_CACHE_DIR", cache),
            patch("gtts.gTTS") as google,
        ):
            google.return_value.write_to_fp.side_effect = lambda buffer: buffer.write(b"google-mp3")
            client = app.test_client()
            for tld in ("com", "com", "co.uk"):
                response = client.get(f"/api/tts?text=hello&lang=en&voice=gtts&tld={tld}")
                self.assertEqual(response.data, b"google-mp3")
            self.assertEqual(google.call_count, 2)

    def test_saturated_synthesis_keeps_cache_available_and_rejects_clip(self):
        started = [threading.Event(), threading.Event()]
        release = threading.Event()
        start_times = [0.0, 0.0]

        def synthesize(text, voice):
            index = int(text[-1])
            start_times[index] = time.monotonic()
            started[index].set()
            if not release.wait(5):
                raise RuntimeError("test timed out")
            return b"mp3"

        with (
            tempfile.TemporaryDirectory() as cache,
            patch("ritdorg.study._TTS_CACHE_DIR", cache),
            patch("ritdorg.app._synthesize_edge", side_effect=synthesize),
            patch("gtts.gTTS") as google,
            patch("ritdorg.bible_fetcher.get_verses", return_value={"1": "clip verse"}),
            ThreadPoolExecutor(max_workers=2) as pool,
        ):
            _study.tts_cache_store("cached", "en", "en-US-GuyNeural", b"cached-mp3")
            futures = [
                pool.submit(lambda i=i: app.test_client().get(f"/api/tts?text=request{i}&lang=en"))
                for i in range(2)
            ]
            try:
                self.assertTrue(all(event.wait(5) for event in started))
                self.assertGreaterEqual(abs(start_times[0] - start_times[1]), 0.49)
                client = app.test_client()
                self.assertEqual(client.get("/api/tts?text=cached&lang=en").data, b"cached-mp3")
                response = client.get("/api/tts?text=other&lang=en")
                self.assertEqual(response.status_code, 503)
                self.assertEqual(response.headers["Retry-After"], "5")
                clip = client.get("/api/clip?book=Genesis&chapter=1&from=1")
                self.assertEqual(clip.status_code, 503)
                google.assert_not_called()
            finally:
                release.set()
            self.assertTrue(all(future.result(timeout=5).status_code == 200 for future in futures))

    def test_failed_synthesis_can_be_retried(self):
        with (
            tempfile.TemporaryDirectory() as cache,
            patch("ritdorg.study._TTS_CACHE_DIR", cache),
            patch("ritdorg.app._synthesize_edge", side_effect=[RuntimeError("offline"), b"mp3"]),
        ):
            client = app.test_client()
            url = "/api/tts?text=retry&lang=en&voice=en-US-AriaNeural"
            self.assertEqual(client.get(url).status_code, 503)
            self.assertEqual(client.get(url).data, b"mp3")

    def test_health_check_remains_responsive_during_voice_synthesis(self):
        from ritdorg.asgi import asgi_app

        started = threading.Event()
        release = threading.Event()

        def synthesize(text, voice):
            started.set()
            if not release.wait(5):
                raise RuntimeError("test timed out")
            return b"mp3"

        async def request_asgi(path, query=b""):
            messages = []
            scope = {
                "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                "method": "GET", "scheme": "http", "path": path, "raw_path": path.encode(),
                "query_string": query, "headers": [], "server": ("localhost", 80),
                "client": ("127.0.0.1", 1234), "root_path": "",
            }

            async def receive():
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(message):
                messages.append(message)

            await asgi_app(scope, receive, send)
            return messages[0]["status"]

        async def exercise():
            pending = asyncio.create_task(request_asgi("/api/tts", b"text=health-test&lang=en"))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 5))
                self.assertEqual(await asyncio.wait_for(request_asgi("/healthz"), 2), 200)
            finally:
                release.set()
                await asyncio.wait_for(pending, 5)

        with (
            tempfile.TemporaryDirectory() as cache,
            patch("ritdorg.study._TTS_CACHE_DIR", cache),
            patch("ritdorg.app._synthesize_edge", side_effect=synthesize),
        ):
            asyncio.run(exercise())

    def test_selected_voice_is_sent_to_the_synthesizer(self):
        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.study.tts_cache_store"),
            patch("ritdorg.app._synthesize_edge", return_value=b"mp3") as synthesize,
        ):
            response = app.test_client().get("/api/tts?text=hello&lang=en&voice=en-US-AriaNeural")
        self.assertEqual(response.status_code, 200)
        synthesize.assert_called_once_with("hello", "en-US-AriaNeural")

    def test_selected_voice_failure_is_not_silently_replaced(self):
        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.app._synthesize_edge", side_effect=RuntimeError("offline")),
        ):
            response = app.test_client().get("/api/tts?text=hello&lang=en&voice=en-US-AriaNeural")
        self.assertEqual(response.status_code, 503)

    def test_selected_voice_empty_audio_is_not_cached(self):
        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.study.tts_cache_store") as store,
            patch("ritdorg.app._synthesize_edge", return_value=b""),
        ):
            response = app.test_client().get("/api/tts?text=hello&lang=en&voice=en-US-AriaNeural")
        self.assertEqual(response.status_code, 503)
        store.assert_not_called()

    def test_unknown_voice_is_rejected(self):
        response = app.test_client().get("/api/tts?text=hello&lang=en&voice=unknown")
        self.assertEqual(response.status_code, 400)

    def test_ai_voice_defaults_and_language_match(self):
        catalog = app.test_client().get("/api/tts/voices").get_json()
        self.assertTrue(any(v["id"] == "es-ES-ElviraNeural" and v["default"] for v in catalog["es"]))
        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.study.tts_cache_store"),
            patch("ritdorg.app._synthesize_edge", return_value=b"mp3") as synthesize,
        ):
            response = app.test_client().get("/api/tts?text=hola&lang=es")
        self.assertEqual(response.status_code, 200)
        synthesize.assert_called_once_with("hola", "es-ES-ElviraNeural")
        response = app.test_client().get("/api/tts?text=hola&lang=es&voice=en-US-AriaNeural")
        self.assertEqual(response.status_code, 400)

    def test_unsupported_neural_language_does_not_use_english_voice(self):
        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.study.tts_cache_store"),
            patch("ritdorg.app._synthesize_edge") as synthesize,
            patch("gtts.gTTS") as google,
        ):
            google.return_value.write_to_fp.side_effect = lambda buffer: buffer.write(b"mp3")
            response = app.test_client().get("/api/tts?text=bonjour&lang=it")
        self.assertEqual(response.status_code, 200)
        synthesize.assert_not_called()
        self.assertEqual(google.call_args.kwargs["lang"], "it")

    def test_learn_align_uses_the_requested_languages_and_keeps_every_target_word(self):
        def verses(translation, book, chapter):
            if translation == 'NIV':
                return {16: 'For God so loved the world'}
            if translation == 'Spanish':
                return {16: 'Porque de tal manera amó Dios al mundo'}
            return {}

        with patch('ritdorg.app._safe_get_verses', side_effect=verses):
            response = app.test_client().get('/api/learn/align/John/3?native=NIV&target=Spanish')
        self.assertEqual(response.status_code, 200)
        verse = response.get_json()['verses']['16']
        glosses = [word for item in verse['words'] for word in item['gloss_words']]
        self.assertEqual(glosses, ['Porque', 'de', 'tal', 'manera', 'amó', 'Dios', 'al', 'mundo'])
        self.assertEqual(response.get_json()['target_lang'], 'es')

    def test_learn_align_rejects_an_unknown_book(self):
        response = app.test_client().get('/api/learn/align/NotABook/1?native=NIV&target=KJV')
        self.assertEqual(response.status_code, 404)

    def test_default_voice_can_still_fall_back_to_google(self):
        def write_audio(buffer):
            buffer.write(b"fallback-mp3")

        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.study.tts_cache_store"),
            patch("ritdorg.app._synthesize_edge", side_effect=RuntimeError("offline")),
            patch("gtts.gTTS") as google,
        ):
            google.return_value.write_to_fp.side_effect = write_audio
            response = app.test_client().get("/api/tts?text=hello&lang=en")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, b"fallback-mp3")


if __name__ == "__main__":
    unittest.main(verbosity=2)
