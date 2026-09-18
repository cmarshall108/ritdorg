#!/usr/bin/env python3
"""Regression tests for security-sensitive production defaults."""
import os
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash

from ritdorg import auth
from ritdorg.app import _DEFAULT_SECRET, _session_secret


class SecurityConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.admin_user = auth.ADMIN_USER
        self.admin_pass_hash = auth.ADMIN_PASS_HASH

    def tearDown(self):
        auth.ADMIN_USER = self.admin_user
        auth.ADMIN_PASS_HASH = self.admin_pass_hash

    def test_missing_admin_hash_does_not_enable_default_password(self):
        auth.ADMIN_USER = "admin"
        auth.ADMIN_PASS_HASH = ""

        auth.ensure_default_admin()

        self.assertEqual(auth.ADMIN_PASS_HASH, "")
        self.assertFalse(auth.verify_admin("admin", "RhemaWeb@1234"))

    def test_configured_admin_password_still_works(self):
        auth.ADMIN_USER = "operator"
        auth.ADMIN_PASS_HASH = generate_password_hash(
            "a-unique-test-password", method="pbkdf2:sha256"
        )

        auth.ensure_default_admin()

        self.assertTrue(auth.verify_admin("operator", "a-unique-test-password"))

    def test_missing_or_known_secret_uses_random_ephemeral_key(self):
        with patch.dict(os.environ, {}, clear=True):
            first = _session_secret()
            second = _session_secret()
        with patch.dict(os.environ, {"SECRET_KEY": _DEFAULT_SECRET}, clear=True):
            known_default = _session_secret()

        self.assertNotEqual(first, second)
        self.assertNotEqual(known_default, _DEFAULT_SECRET)
        self.assertGreaterEqual(len(first), 64)

    def test_configured_session_secret_is_preserved(self):
        with patch.dict(os.environ, {"SECRET_KEY": "unique-production-secret"}, clear=True):
            self.assertEqual(_session_secret(), "unique-production-secret")


if __name__ == "__main__":
    unittest.main()