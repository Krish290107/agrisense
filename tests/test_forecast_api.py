"""Service and ASGI HTTP tests using isolated SQLite files, without extra clients."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app import app
from backend.forecast_api import ForecastResult
from backend.forecast_service import (generate_forecast, rolling_mean, open_repository,
                                      ForecastUnavailable, SeriesNotFound)
from database.store import Repository, series_id


def request(application, method, path, body=None, headers=None):
    async def dispatch():
        parsed = urlsplit(path)
        payload = json.dumps(body).encode() if body is not None else b""
        scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.4"}, "http_version": "1.1",
                 "method": method, "scheme": "http", "path": parsed.path, "raw_path": parsed.path.encode(),
                 "query_string": parsed.query.encode(), "root_path": "", "server": ("test", 80), "client": ("test", 1),
                 "headers": [(b"content-type", b"application/json"), *[(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]]}
        sent, messages = False, []

        async def receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": payload, "more_body": False}
            await asyncio.Event().wait()

        async def send(message):
            messages.append(message)

        await asyncio.wait_for(application(scope, receive, send), timeout=10)
        start = next(m for m in messages if m["type"] == "http.response.start")
        content = b"".join(m.get("body", b"") for m in messages if m["type"] == "http.response.body")
        result_headers = {k.decode(): v.decode() for k, v in start["headers"]}
        decoded = json.loads(content) if "application/json" in result_headers.get("content-type", "") else content.decode()
        return start["status"], decoded, result_headers
    return asyncio.run(dispatch())


class ForecastTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.db"
        self.url = "sqlite:///" + self.path.as_posix()
        self.previous_url = getattr(app.state, "database_url", None)
        app.state.database_url = self.url
        base = {"state": "Gujarat", "district": "Dahod", "market": "Test", "commodity": "Onion", "variety": "Onion", "grade": "FAQ"}
        self.identities = {"rolling": base, "naive": {**base, "grade": "Non-FAQ"},
                           "short": {**base, "variety": "Other"}, "empty": {**base, "market": "Empty"},
                           "unsupported": {**base, "market": "Unsupported"}}
        self.ids = {name: series_id(identity) for name, identity in self.identities.items()}
        with Repository(self.url) as repo:
            repo.initialize()
            for name, identity in self.identities.items():
                repo._put("series", {"series_id": self.ids[name], **identity, "price_unit": "INR/quintal"}, ["series_id"])
                prices = {"rolling": range(100, 900, 100), "naive": [3000, 3500, 4000], "short": [123, 456], "empty": [], "unsupported": [555]}[name]
                for index, price in enumerate(prices):
                    repo._put("observations", {"series_id": self.ids[name], "date": (date(2024, 1, 1) + timedelta(days=index*2)).isoformat(),
                               "min_price": "1", "modal_price": str(price), "max_price": "999999",
                               "source_sha256": "a"*64, "source_record": index+1}, ["series_id", "date"])
            entries = []
            for name in ["rolling", "naive", "short", "empty"]:
                naive = name == "naive"
                entries.append({"series_id": self.ids[name], "identity": self.identities[name], "evaluation_version": "fixture-v1",
                                "selected_method": "naive" if naive else "rolling_mean_7", "window": None if naive else 7,
                                "minimum_history": 1 if naive else 7, "fallback_method": "naive", "benchmark_mae": 10, "status": "selected"})
            policy = Path(self.temp.name) / "policy.json"
            policy.write_text(json.dumps({"schema_version": 1, "evaluation_version": "fixture-v1", "unit": "INR/quintal",
                                          "ml_status": "experimental_not_selected", "series": entries}), encoding="utf-8")
            repo.import_policy(policy)

    def tearDown(self):
        app.state.database_url = self.previous_url
        self.temp.cleanup()

    def calculate(self, name, **kwargs):
        with open_repository(self.url) as repo:
            return generate_forecast(repo, self.ids[name], **kwargs)

    def test_naive_and_exact_latest_seven_without_crossing_grade(self):
        naive = self.calculate("naive", persist=False)
        self.assertEqual(naive["prediction"], "4000")
        self.assertEqual(naive["history_observations_used"], 1)
        rolling = self.calculate("rolling", persist=False)
        self.assertEqual(rolling["prediction"], "500.000000")
        self.assertEqual(rolling["history_observations_used"], 7)
        self.assertEqual(rolling["history_start_date"], "2024-01-03")
        self.assertEqual(rolling["history_cutoff_date"], "2024-01-15")
        self.assertEqual(rolling["method_used"], "rolling_mean_7")
        self.assertFalse(rolling["fallback_used"])
        self.assertEqual(rolling["series"]["grade"], "FAQ")
        self.assertEqual(rolling["forecast_type"], "next_observation")

    def test_fallback_and_as_of_exclude_later_observations(self):
        result = self.calculate("short", persist=False)
        self.assertEqual(result["prediction"], "456")
        self.assertTrue(result["fallback_used"])
        self.assertEqual(result["selected_method"], "rolling_mean_7")
        self.assertEqual(result["method_used"], "naive")
        self.assertEqual(result["history_observations_used"], 1)
        historical = self.calculate("rolling", as_of_date="2024-01-13", persist=False)
        self.assertEqual(historical["prediction"], "400.000000")
        self.assertEqual(historical["history_cutoff_date"], "2024-01-13")
        with Repository(self.url) as repo:
            repo.connection.execute("UPDATE observations SET modal_price='99999' WHERE series_id=? AND date>'2024-01-13'", (self.ids["rolling"],))
        self.assertEqual(self.calculate("rolling", as_of_date="2024-01-13", persist=False)["prediction"], historical["prediction"])

    def test_no_history_unsupported_and_unknown(self):
        for name, status in [("empty", "insufficient_history"), ("unsupported", "unsupported_series")]:
            result = self.calculate(name)
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["prediction"])
            self.assertIsNone(result["forecast_id"])
        self.assertEqual(self.calculate("rolling", as_of_date="2023-01-01")["status"], "insufficient_history")
        with Repository(self.url) as repo:
            self.assertEqual(repo.summary()["table_counts"]["forecasts"], 0)
            with self.assertRaises(SeriesNotFound):
                generate_forecast(repo, "0"*16)

    def test_decimal_precision_and_half_even(self):
        self.assertEqual(rolling_mean(["1"]*6 + ["2"]), "1.142857")
        self.assertEqual(rolling_mean(["1.0000005"]*7), "1.000000")
        self.assertEqual(rolling_mean(["1.0000015"]*7), "1.000002")
        self.assertEqual(Decimal(rolling_mean(["1599.99"]*7)), Decimal("1599.99"))

    def test_persistence_idempotency_and_history_change(self):
        first = self.calculate("rolling")
        self.assertEqual(self.calculate("rolling"), first)
        with Repository(self.url) as repo:
            stored = repo.get_forecast(first["forecast_id"])
            self.assertEqual(stored["prediction"], first["prediction"])
            self.assertIsNone(stored["target_date"])
            self.assertEqual(len(repo.forecast_history(self.ids["rolling"])), 1)
            repo._put("observations", {"series_id": self.ids["rolling"], "date": "2024-01-17", "min_price": "1",
                       "modal_price": "900", "max_price": "9999", "source_sha256": "b"*64, "source_record": 9}, ["series_id", "date"])
        changed = self.calculate("rolling")
        self.assertNotEqual(changed["forecast_id"], first["forecast_id"])
        self.assertEqual(changed["prediction"], "600.000000")

    def test_concurrent_retries_create_one_forecast(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: self.calculate("rolling"), range(2)))
        self.assertEqual(results[0], results[1])
        with Repository(self.url) as repo:
            self.assertEqual(repo.summary()["table_counts"]["forecasts"], 1)

    def test_read_only_dry_run_does_not_change_database(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with open_repository(self.url, read_only=True) as repo:
            result = generate_forecast(repo, self.ids["rolling"], persist=False)
        self.assertIsNone(result["forecast_id"])
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), before)

    def test_nonselected_method_fails_closed(self):
        with Repository(self.url) as repo:
            repo.connection.execute("UPDATE policies SET selected_method='historical_mean',window=NULL,minimum_history=1 WHERE series_id=?", (self.ids["rolling"],))
        with self.assertRaises(ForecastUnavailable):
            self.calculate("rolling")

    def test_persistence_failure_rolls_back_and_http_error_is_sanitized(self):
        with patch.object(Repository, "save_forecast", side_effect=ValueError("private SQL or filesystem detail")):
            status, result, _ = request(app, "POST", "/api/v1/forecast", {"series_id": self.ids["rolling"]})
        self.assertEqual(status, 503)
        self.assertNotIn("private", json.dumps(result))
        with Repository(self.url) as repo:
            self.assertEqual(repo.summary()["table_counts"]["forecasts"], 0)

    def test_http_health_discovery_history_and_docs(self):
        self.assertEqual(request(app, "GET", "/health")[:2], (200, {"status": "ok", "service": "agrisense-api"}))
        status, series, _ = request(app, "GET", "/api/v1/forecast/series")
        self.assertEqual(status, 200)
        self.assertEqual(len(series), 4)
        self.assertEqual([r["series_id"] for r in series], sorted(r["series_id"] for r in series))
        status, result, _ = request(app, "GET", f"/api/v1/forecast/series/{self.ids['rolling']}/history?limit=2")
        self.assertEqual(status, 200)
        self.assertEqual([r["modal_price"] for r in result["observations"]], ["700", "800"])
        self.assertNotIn("source_sha256", result["observations"][0])
        self.assertEqual(request(app, "GET", "/openapi.json")[0], 200)
        self.assertIn('a.link[href="/openapi.json"]', request(app, "GET", "/docs")[1])

    def test_http_success_fallback_persistence_and_schema(self):
        for name, prediction, fallback in [("naive", "4000", False), ("rolling", "500.000000", False), ("short", "456", True)]:
            status, result, _ = request(app, "POST", "/api/v1/forecast", {"series_id": self.ids[name]})
            self.assertEqual(status, 200)
            ForecastResult.model_validate(result)
            self.assertEqual(result["prediction"], prediction)
            self.assertEqual(result["fallback_used"], fallback)
            self.assertNotIn("confidence", result)
            again = request(app, "POST", "/api/v1/forecast", {"series_id": self.ids[name]})[1]
            self.assertEqual(result, again)
            saved = request(app, "GET", f"/api/v1/forecast/series/{self.ids[name]}/forecasts?limit=1")[1]
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0]["forecast_id"], result["forecast_id"])

    def test_http_unknown_unsupported_empty_and_invalid(self):
        self.assertEqual(request(app, "POST", "/api/v1/forecast", {"series_id": "0"*16})[0], 404)
        for name, status in [("unsupported", "unsupported_series"), ("empty", "insufficient_history")]:
            code, result, _ = request(app, "POST", "/api/v1/forecast", {"series_id": self.ids[name]})
            self.assertEqual(code, 200)
            self.assertEqual(result["status"], status)
            self.assertIsNone(result["prediction"])
        for body in [{}, {"series_id": 123}, {"series_id": "x"}, {"series_id": self.ids["rolling"], "target_date": "2027-01-01"},
                     {"series_id": self.ids["rolling"], "as_of_date": "2024-02-30"}, {"series_id": self.ids["rolling"], "as_of_date": "20240101"}]:
            self.assertEqual(request(app, "POST", "/api/v1/forecast", body)[0], 422)
        for suffix in ["history?limit=0", "history?limit=366", "forecasts?limit=101", "forecasts?limit=-1"]:
            self.assertEqual(request(app, "GET", f"/api/v1/forecast/series/{self.ids['rolling']}/{suffix}")[0], 422)
        result = request(app, "POST", "/api/v1/forecast", {"series_id": self.ids["rolling"], "as_of_date": "2024-01-03"})[1]
        self.assertEqual(result["prediction"], "200")
        self.assertTrue(result["fallback_used"])

    def test_http_missing_empty_or_invalid_database_is_sanitized(self):
        missing = Path(self.temp.name) / "missing.db"
        app.state.database_url = "sqlite:///" + missing.as_posix()
        code, result, _ = request(app, "GET", "/api/v1/forecast/series")
        self.assertEqual(code, 503)
        self.assertFalse(missing.exists())
        self.assertNotIn(str(missing), json.dumps(result))
        self.assertEqual(request(app, "GET", "/health")[0], 200)
        with Repository(app.state.database_url) as repo:
            repo.initialize()
        self.assertEqual(request(app, "GET", "/api/v1/forecast/series")[0], 503)
        app.state.database_url = self.url
        with Repository(self.url) as repo:
            repo.connection.execute("DELETE FROM schema_info")
        self.assertEqual(request(app, "GET", "/api/v1/forecast/series")[0], 503)

    def test_cors_keeps_origins_and_allows_forecast_post(self):
        status, _, headers = request(app, "OPTIONS", "/api/v1/forecast", headers={
            "Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
        self.assertEqual(status, 200)
        self.assertEqual(headers["access-control-allow-origin"], "http://localhost:3000")
        self.assertIn("POST", headers["access-control-allow-methods"])
        self.assertNotIn("access-control-allow-origin", request(app, "GET", "/health", headers={"Origin": "https://untrusted.example"})[2])


if __name__ == "__main__":
    unittest.main()
