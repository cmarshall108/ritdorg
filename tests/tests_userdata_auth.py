#!/usr/bin/env python3
"""User data (me/*) and auth related endpoint tests.

Covers reading state, bookmarks, notes, highlights, the three export endpoints,
device vs logged-in ownership, and basic auth flows (save-email, logout).
"""
import os
import json
import tempfile
import shutil
import unittest
from pathlib import Path

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


class UserDataAuthTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.static_root = Path(appmod.app.static_folder)
        cls.client = app.test_client()

    @classmethod
    def tearDownClass(cls):
        try:
            shutil.rmtree(TEST_TMP, ignore_errors=True)
        except Exception:
            pass

    def _with_device(self):
        """Return a fresh client pre-configured with a stable device key (anonymous path)."""
        c = app.test_client()
        c.set_cookie("ritd_device", "test-userdata-device-001")
        return c

    def test_state_roundtrip(self):
        c = self._with_device()
        # save
        r = c.put("/api/me/state", json={"book": "Genesis", "chapter": 3, "verse": 5, "view": "reader"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get("ok"))

        # load
        r = c.get("/api/me/state")
        self.assertEqual(r.status_code, 200)
        st = r.get_json()
        self.assertEqual(st.get("book"), "Genesis")
        self.assertEqual(st.get("chapter"), 3)

    def test_bookmarks_crud(self):
        c = self._with_device()
        r = c.post("/api/me/bookmarks", json={"book": "Exodus", "chapter": 1, "verse": 1, "label": "Start"})
        self.assertEqual(r.status_code, 200)
        bid = r.get_json().get("id")
        self.assertIsNotNone(bid)

        r = c.get("/api/me/bookmarks")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(b["id"] == bid for b in r.get_json().get("bookmarks", [])))

        r = c.delete(f"/api/me/bookmarks/{bid}")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.get_json().get("ok"))

    def test_notes_crud(self):
        c = self._with_device()
        r = c.post("/api/me/notes", json={"book": "Leviticus", "chapter": 1, "verse": 1, "body": "My note"})
        self.assertEqual(r.status_code, 200)
        nid = r.get_json().get("id")

        r = c.get("/api/me/notes?book=Leviticus&chapter=1")
        self.assertEqual(r.status_code, 200)
        notes = r.get_json().get("notes", [])
        self.assertTrue(any(n["id"] == nid for n in notes))

        r = c.delete(f"/api/me/notes/{nid}")
        self.assertEqual(r.status_code, 200)

    def test_highlights_set_clear(self):
        c = self._with_device()
        r = c.post("/api/me/highlights", json={"book": "Numbers", "chapter": 2, "verse": 3, "color": "yellow"})
        self.assertEqual(r.status_code, 200)
        hid = r.get_json().get("id")

        r = c.get("/api/me/highlights?book=Numbers&chapter=2")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(any(h["id"] == hid for h in r.get_json().get("highlights", [])))

        # clear by posting empty color
        r = c.post("/api/me/highlights", json={"book": "Numbers", "chapter": 2, "verse": 3, "color": ""})
        self.assertEqual(r.status_code, 200)

    def test_export_notes_bookmarks_chapter(self):
        c = self._with_device()
        # seed a note + bookmark so exports have content
        c.post("/api/me/notes", json={"book": "Genesis", "chapter": 1, "verse": 1, "body": "Export test"})
        c.post("/api/me/bookmarks", json={"book": "Genesis", "chapter": 1, "verse": 1})

        r = c.get("/api/me/export/notes")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/markdown", r.content_type)

        r = c.get("/api/me/export/bookmarks")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/markdown", r.content_type)

        r = c.get("/api/me/export/chapter/Genesis/1?translation=NIV")
        self.assertEqual(r.status_code, 200)
        self.assertIn("text/markdown", r.content_type)

    def test_auth_save_email_and_logout(self):
        c = app.test_client()
        r = c.post("/auth/save-email", json={"email": "userdata-test@example.com"})
        # JSON path returns 200; form path may redirect
        self.assertIn(r.status_code, (200, 302))
        # subsequent request should see a user
        r2 = c.get("/api/me/state")
        self.assertEqual(r2.status_code, 200)

        r3 = c.get("/logout")
        self.assertIn(r3.status_code, (200, 302))

    def test_device_vs_user_ownership_isolation(self):
        # Two different devices should not see each other's anonymous data
        c1 = app.test_client()
        c1.set_cookie("ritd_device", "dev-one-111")
        c1.post("/api/me/bookmarks", json={"book": "Psalms", "chapter": 1, "verse": 1})

        c2 = app.test_client()
        c2.set_cookie("ritd_device", "dev-two-222")
        r = c2.get("/api/me/bookmarks")
        bms = r.get_json().get("bookmarks", [])
        self.assertFalse(any(b.get("book") == "Psalms" for b in bms))


if __name__ == "__main__":
    unittest.main(verbosity=2)
