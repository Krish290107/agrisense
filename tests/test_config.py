import unittest
from unittest.mock import patch

from backend.app import DEFAULT_ALLOWED_ORIGINS, app, parse_origins
from database.store import ROOT, database_path
from tests.test_forecast_api import request


class ConfigTests(unittest.TestCase):
    def test_explicit_origins_and_sanitized_invalid_config(self):
        self.assertEqual(parse_origins(" https://example.com/,https://example.com "), ["https://example.com"])
        self.assertEqual(len(parse_origins(DEFAULT_ALLOWED_ORIGINS)), 2)
        for value in ["", "*", "null", "ftp://example.com", "https://example.com/path", "https://secret@example.com", "https://example.com?secret", "http://localhost:bad"]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "ALLOWED_ORIGINS must"):
                parse_origins(value)

    def test_database_defaults_invalid_config_and_cors(self):
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(database_path(), ROOT / "data/agrisense.db")
        with self.assertRaises(ValueError):
            database_path("postgresql://private:secret@host/db")
        status, _, headers = request(app, "OPTIONS", "/api/v1/forecast", headers={"Origin":"http://localhost:3000", "Access-Control-Request-Method":"POST"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["access-control-allow-origin"], "http://localhost:3000")
        status, _, headers = request(app, "OPTIONS", "/api/v1/forecast", headers={"Origin":"https://untrusted.invalid", "Access-Control-Request-Method":"POST"})
        self.assertEqual(status, 400)
        self.assertNotIn("access-control-allow-origin", headers)
