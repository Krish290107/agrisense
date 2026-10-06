import unittest
from unittest.mock import patch

from backend.app import app
from backend.decision_api import price_signal
from backend.forecast_service import generate_forecast
from backend.forecast_service import ForecastUnavailable
from database.store import Repository
from tests import test_forecast_api as fixtures


class DecisionTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ForecastTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def get(self, name):
        return fixtures.request(app, "GET", "/api/v1/decision/markets?series_id=" + self.fixture.ids[name])

    def test_exact_scope_reuses_service_readonly_and_keeps_missing_null(self):
        with patch("backend.decision_api.generate_forecast", wraps=generate_forecast) as service:
            status, result, _ = self.get("rolling")
        self.assertEqual(status, 200)
        self.assertEqual(result["scope"], "exact_variety_grade")
        self.assertEqual(len(result["markets"]), 2)
        self.assertEqual(service.call_count, 2)
        self.assertTrue(all(call.kwargs == {"persist": False} for call in service.call_args_list))
        first, empty = result["markets"]
        self.assertEqual(first["forecast"]["series"]["series_id"], self.fixture.ids["rolling"])
        self.assertEqual(first["forecast"]["prediction"], "500.000000")
        self.assertEqual(float(first["difference"]), -300)
        self.assertEqual(float(first["percentage"]), -37.5)
        self.assertEqual(first["signal"], "below")
        self.assertIsNone(empty["forecast"]["prediction"])
        self.assertIsNone(empty["difference"])
        with Repository(self.fixture.url) as repo:
            self.assertEqual(repo.connection.execute("SELECT COUNT(*) FROM forecasts").fetchone()[0], 0)

    def test_broader_scope_active_only_sorted_and_identity_preserved(self):
        status, result, _ = self.get("naive")
        self.assertEqual(status, 200)
        self.assertEqual(result["scope"], "commodity")
        self.assertIn("different varieties or grades", result["warning"])
        rows = result["markets"]
        self.assertEqual(len(rows), 4)
        self.assertNotIn(self.fixture.ids["unsupported"], [r["forecast"]["series"]["series_id"] for r in rows])
        self.assertEqual([r["forecast"]["prediction"] for r in rows], ["4000", "500.000000", "456", None])
        self.assertEqual(rows[0]["forecast"]["series"]["grade"], "Non-FAQ")
        self.assertTrue(all(r["forecast"]["method_used"] in ("naive", "rolling_mean_7", None) for r in rows))
        self.assertEqual(self.get("naive")[1]["markets"][0]["forecast"]["series"], rows[0]["forecast"]["series"])

    def test_signal_boundaries_and_unavailable(self):
        for estimate, expected in [("101.99", "near"), ("102", "above"), ("98", "below"), ("100", "near")]:
            self.assertEqual(price_signal("100", estimate)["signal"], expected)
        self.assertIsNone(price_signal(None, "100")["difference"])
        self.assertIsNone(price_signal("0", "100")["percentage"])

    def test_errors(self):
        self.assertEqual(self.get("unsupported")[0], 422)
        self.assertEqual(fixtures.request(app, "GET", "/api/v1/decision/markets?series_id=" + "f"*16)[0], 404)
        self.assertEqual(fixtures.request(app, "GET", "/api/v1/decision/markets?series_id=invalid")[0], 422)
        with patch("backend.decision_api.generate_forecast", side_effect=ForecastUnavailable("private path")):
            status, result, _ = self.get("rolling")
        self.assertEqual(status, 503)
        self.assertNotIn("private path", str(result))


if __name__ == "__main__":
    unittest.main()
