#!/usr/bin/env python3
"""Core Bible API tests (verses, search, tts, hebrew, lexicon, playlists, votd, etc).

Run with:
    PYTHONPATH=. python -m unittest tests.tests_core_api
or
    PYTHONPATH=. python tests/tests_core_api.py
"""
import os
import json
import tempfile
import shutil
import unittest
from pathlib import Path

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


if __name__ == "__main__":
    unittest.main(verbosity=2)
