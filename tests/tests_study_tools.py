#!/usr/bin/env python3
"""Study tools API tests: tags, outlines, playlists, plans, crossrefs, interlinear,
footnotes, clip, notebooks, settings, timeline, concordance, hebrew lemma, exports, etc.

These exercise the study_bp routes and related helpers.
"""
import os
import json
import tempfile
import shutil
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_TMP = tempfile.mkdtemp(prefix="ritdorg-test-")
TEST_DB = os.path.join(TEST_TMP, "auth.db")
os.environ["AUTH_DB_PATH"] = TEST_DB

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
    cache_dir = static_root / "data" / "bible" / "niv" / "Genesis"
    cache_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "1": "In the beginning God created the heaven and the earth.",
        "2": "And the earth was without form, and void.",
        "3": "And God said, Let there be light.",
    }
    (cache_dir / "1.json").write_text(json.dumps(data), encoding="utf-8")


def _cleanup_seed(static_root: Path) -> None:
    p = static_root / "data" / "bible" / "niv" / "Genesis" / "1.json"
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


class StudyToolsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static_root = Path(appmod.app.static_folder)
        _seed_minimal_corpus(cls.static_root)
        cls.client = app.test_client()
        # Ensure a device key for anonymous study data (tags/outlines/playlists)
        cls.client.set_cookie("ritd_device", "test-device-study-xyz")
        # Also create a logged-in user for notebook tests (notebooks require real user_id)
        cls._login_for_notebooks()

    @classmethod
    def _login_for_notebooks(cls):
        # Directly create a user + session token and inject the cookie.
        # This is more reliable in the test client than relying on the view's
        # make_response + set_cookie roundtrip (which can be sensitive to
        # is_json / wants_json detection and cookie jar propagation when
        # other cookies like device are already present).
        try:
            uid = _auth.get_or_create_user("study-test@example.com")
            token, _ = _auth.create_session(uid, ip="127.0.0.1", user_agent="test-client")
            cls.client.set_cookie(_auth.SESSION_COOKIE_NAME, token)
            cls._logged_in = True
        except Exception:
            cls._logged_in = False

    @classmethod
    def tearDownClass(cls):
        _cleanup_seed(cls.static_root)
        try:
            shutil.rmtree(TEST_TMP, ignore_errors=True)
        except Exception:
            pass

    # --- Tags (#1) ---
    def test_tags_crud(self):
        # create
        r = self.client.post("/api/me/tags", json={"name": "TestTag", "color": "#ffcc00"})
        self.assertEqual(r.status_code, 200)
        tag = r.get_json()
        self.assertTrue(tag.get("ok"))
        tag_id = tag.get("id")
        self.assertIsNotNone(tag_id)

        # list
        r = self.client.get("/api/me/tags")
        self.assertEqual(r.status_code, 200)
        lst = r.get_json().get("tags", [])
        self.assertTrue(any(t["id"] == tag_id for t in lst))

        # link a verse
        r = self.client.post("/api/me/tag-link", json={
            "tag_id": tag_id, "book": "Genesis", "chapter": 1, "verse": 1
        })
        self.assertEqual(r.status_code, 200)

        # get verses for tag
        r = self.client.get(f"/api/me/tags/{tag_id}/verses")
        self.assertEqual(r.status_code, 200)
        verses = r.get_json().get("verses", [])
        self.assertTrue(any(v["book"] == "Genesis" for v in verses))

        # unlink
        r = self.client.delete(f"/api/me/tag-link/{tag_id}/Genesis/1/1")
        self.assertEqual(r.status_code, 200)

        # delete tag
        r = self.client.delete(f"/api/me/tags/{tag_id}")
        self.assertEqual(r.status_code, 200)

    # --- Outlines (#2) ---
    def test_outlines_crud_and_export(self):
        r = self.client.post("/api/me/outlines", json={
            "title": "My Outline", "theme": "Creation", "body_md": "Intro..."
        })
        self.assertEqual(r.status_code, 200)
        oid = r.get_json().get("id")
        self.assertIsNotNone(oid)

        r = self.client.get("/api/me/outlines")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(o["id"] == oid for o in r.get_json()["outlines"]))

        # Set verses via the supported update payload (no dedicated /verses subroute)
        r = self.client.put(f"/api/me/outlines/{oid}", json={
            "title": "My Outline",
            "verses": [{"book": "Genesis", "chapter": 1, "verse": 1, "label": "Start"}]
        })
        self.assertEqual(r.status_code, 200)

        # export (uses bible_fetcher internally - now with relative import fix)
        r = self.client.get(f"/api/me/outlines/{oid}/export?translation=NIV")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/markdown", r.content_type)

        # update
        r = self.client.put(f"/api/me/outlines/{oid}", json={"title": "Updated"})
        self.assertEqual(r.status_code, 200)

        # delete
        r = self.client.delete(f"/api/me/outlines/{oid}")
        self.assertEqual(r.status_code, 200)

    # --- Playlists (#3) ---
    def test_playlists_crud(self):
        r = self.client.post("/api/me/playlists", json={"name": "My Reading List"})
        self.assertEqual(r.status_code, 200)
        pid = r.get_json().get("id")

        r = self.client.post(f"/api/me/playlists/{pid}/items", json={
            "book": "Genesis", "chapter": 1, "verse": 1
        })
        self.assertEqual(r.status_code, 200)

        r = self.client.get(f"/api/me/playlists/{pid}")
        self.assertEqual(r.status_code, 200)
        pdata = r.get_json() or {}
        items = pdata.get("playlist", {}).get("items", [])
        self.assertGreaterEqual(len(items), 1)

        # delete item then playlist
        item_id = items[0]["id"]
        r = self.client.delete(f"/api/me/playlists/{pid}/items/{item_id}")
        self.assertEqual(r.status_code, 200)

        r = self.client.delete(f"/api/me/playlists/{pid}")
        self.assertEqual(r.status_code, 200)

    # --- Reading plans (#4) ---
    def test_plans_and_progress(self):
        r = self.client.get("/api/plans")
        self.assertEqual(r.status_code, 200)
        plans = r.get_json().get("plans", [])
        self.assertIsInstance(plans, list)
        if plans:
            slug = plans[0]["slug"]
            r = self.client.get(f"/api/plans/{slug}")
            self.assertEqual(r.status_code, 200)

            # progress (anonymous ok)
            r = self.client.post(f"/api/me/plans/{slug}/progress", json={"day": 1, "completed": True})
            self.assertEqual(r.status_code, 200)

    # --- Cross references (#5) ---
    def test_crossrefs(self):
        r = self.client.get("/api/crossrefs/Genesis/1/1")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("crossrefs", data)

    # --- Interlinear (#11) ---
    def test_interlinear(self):
        r = self.client.get("/api/interlinear/Genesis/1")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("verses", data)

    # --- Footnotes (#15) ---
    def test_footnotes(self):
        r = self.client.get("/api/footnotes/Genesis/1")
        self.assertEqual(r.status_code, 200)
        # May be empty list or object; just no crash
        self.assertIsInstance(r.get_json(), (dict, list))

    # --- Audio clip (#13) ---
    def test_audio_clip(self):
        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.study.tts_cache_store"),
            patch("ritdorg.app._synthesize_edge", return_value=b"test-mp3"),
        ):
            r = self.client.get(
                "/api/clip?book=Genesis&chapter=1&from=1&to=2&translation=NIV"
            )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.mimetype, "audio/mpeg")
        self.assertGreater(len(r.data), 0)

    def test_audio_clip_limits_and_unavailable_service(self):
        r = self.client.get(
            "/api/clip?book=Genesis&chapter=1&from=1&to=31&translation=NIV"
        )
        self.assertEqual(r.status_code, 400)
        r = self.client.get(
            "/api/clip?book=Genesis&chapter=0&from=1&to=1&translation=NIV"
        )
        self.assertEqual(r.status_code, 400)
        with (
            patch("ritdorg.study.tts_cache_lookup", return_value=None),
            patch("ritdorg.study.tts_cache_store"),
            patch("ritdorg.app._synthesize_edge", side_effect=RuntimeError("offline")),
        ):
            r = self.client.get(
                "/api/clip?book=Genesis&chapter=1&from=1&to=1&translation=NIV"
            )
        self.assertEqual(r.status_code, 503)

    # --- Notebooks (#16) - requires login ---
    def test_notebooks_require_login_and_crud(self):
        if not getattr(self, "_logged_in", False):
            self.skipTest("Could not establish login session for notebook test")
        anonymous = app.test_client()
        r = anonymous.get("/api/me/notebooks")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json()["needs_login"])
        r = anonymous.post("/api/me/notebooks", json={"title": "Anonymous"})
        self.assertEqual(r.status_code, 401)

        r = self.client.get("/api/me/notebooks")
        self.assertEqual(r.status_code, 200)

        r = self.client.post("/api/me/notebooks", json={"title": "Test Notebook"})
        self.assertEqual(r.status_code, 200)
        nb = r.get_json()
        self.assertTrue(nb.get("ok"))
        nid = nb.get("id")

        r = self.client.get("/api/me/notebooks")
        self.assertEqual(r.status_code, 200)
        lst = r.get_json().get("notebooks", [])
        self.assertTrue(any(n["id"] == nid for n in lst))

        r = self.client.post(f"/api/me/notebooks/{nid}/entries", json={
            "book": "Genesis", "chapter": 1, "verse": 1, "body_md": "Note here"
        })
        self.assertEqual(r.status_code, 200)

        r = self.client.get(f"/api/me/notebooks/{nid}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["entries"][0]["body_md"], "Note here")

        token = nb.get("share_token")
        self.assertTrue(token)
        r = self.client.post(f"/api/notebooks/join/{token}")
        self.assertEqual(r.status_code, 200)

    # --- Settings (#17) ---
    def test_me_settings(self):
        r = self.client.get("/api/me/settings")
        self.assertEqual(r.status_code, 200)
        s = r.get_json()
        self.assertIn("settings", s)

        r = self.client.post("/api/me/settings", json={"tts_voice": "en-US-AvaNeural"})
        self.assertEqual(r.status_code, 200)

    # --- Timeline (#18) ---
    def test_timeline(self):
        r = self.client.get("/api/timeline")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("books", data)

    # --- Concordance / words search / hebrew lemma (corpus backed) ---
    def test_concordance(self):
        r = self.client.get("/api/words/concordance?word=God&translations=NIV")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("breakdown", data)

    def test_words_search(self):
        r = self.client.get("/api/words/search?q=beginning&translation=NIV")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("results", data)

    def test_hebrew_lemma_search(self):
        r = self.client.get("/api/hebrew/lemma-search?word=%D7%90&limit=5")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("roots", data)

    def test_hebrew_lemma_bridge(self):
        entry = {
            "lemma": "בָּרָא",
            "strongs_def": "to create",
            "kjv_def": "create, make",
        }
        with (
            patch("ritdorg.app._load_hebrew_dict", return_value=({}, {})),
            patch("ritdorg.lexicon.search", return_value=[entry]),
        ):
            r = self.client.get("/api/hebrew/lemma-bridge?word=%D7%91%D7%A8%D7%90")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["gloss"], "to create")
        self.assertIn("create", r.get_json()["candidates"])

    def test_lexicon_search_matches_unpointed_hebrew(self):
        from ritdorg import lexicon
        entries = {
            "H1254": {
                "id": "H1254",
                "lemma": "בָּרָא",
                "translit": "bârâʼ",
                "pron": "baw-raw'",
                "strongs_def": "to create",
                "kjv_def": "create, make",
            }
        }
        with (
            patch.object(lexicon, "_load", return_value=entries),
            patch.dict(lexicon._index, {"hebrew": lexicon._build_index(entries, "hebrew")}),
        ):
            results = lexicon.search("hebrew", "ברא")
        self.assertEqual([result["id"] for result in results], ["H1254"])

    def test_parallel_translation_endpoint_for_presentations(self):
        r = self.client.get(
            "/api/verses/parallel/Genesis/1"
            "?translation1=NIV&translation2=Hebrew"
        )
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("1", data["translation1"]["verses"])

    # --- Exports ---
    def test_export_all(self):
        r = self.client.get("/api/me/export/all")
        self.assertEqual(r.status_code, 200)
        self.assertIn("application/zip", r.content_type or "")

    def test_corpus_availability(self):
        r = self.client.get("/api/corpus/availability")
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn("available", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
