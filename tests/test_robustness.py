"""Contracts for Day 8 origins, diagnostics and safe policy execution."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from evaluate_robustness import (error_metrics, gap_band, shock, windows, make_policy,
                                 validate_policy, load_policy, policy_forecast, verify_hashes)
from market_data_common import SERIES_FIELDS, file_digest

IDENTITY = dict(zip(SERIES_FIELDS, ["Gujarat", "Test", "Market", "Onion", "Other", "FAQ"]))


def policy():
    return make_policy(pd.DataFrame([{**IDENTITY, "series_id": "example", "baseline": "rolling_mean_7", "mae": 12.5}]))


def history(prices):
    return pd.DataFrame([{**IDENTITY, "date": date, "modal_price": price}
                         for date, price in zip(pd.date_range("2024-01-01", periods=len(prices)), prices)])


class RobustnessTests(unittest.TestCase):
    def test_metrics_and_direction(self):
        result = error_metrics([100, 100, 100], [110, 80, 100])
        self.assertEqual(result["mae"], 10)
        self.assertAlmostEqual(result["rmse"], np.sqrt(500 / 3))
        self.assertAlmostEqual(result["bias"], -10 / 3)
        self.assertEqual(result["median_signed_error"], 0)
        self.assertAlmostEqual(result["over_rate"], 1 / 3)
        self.assertAlmostEqual(result["under_rate"], 1 / 3)
        self.assertAlmostEqual(result["smape"], 200 * (10 / 210 + 20 / 180) / 3)
        self.assertEqual(error_metrics([0], [0])["smape"], 0)
        for a, p in [([], []), ([1], [np.nan]), ([1], [1, 2])]:
            with self.assertRaises(ValueError):
                error_metrics(a, p)

    def test_chronological_origins_and_expansion(self):
        frame = history(range(100, 190))
        frame["split"] = ["train"] * 20 + ["validation"] * 10 + ["test"] * 60
        seen = []
        for number, past, block in windows(frame):
            self.assertEqual(len(past), 30 + (number - 1) * 20)
            self.assertLess(past.date.max(), block.date.min())
            self.assertTrue(set(past.index).isdisjoint(block.index))
            self.assertEqual(len(block), 20)
            seen.extend(block.index)
        self.assertEqual(seen, list(range(30, 90)))
        mutated = frame.copy()
        mutated.loc[mutated.split.eq("test"), "modal_price"] = 99999
        pd.testing.assert_frame_equal(next(windows(frame))[1], next(windows(mutated))[1])
        frame.loc[0, "grade"] = "different"
        with self.assertRaises(ValueError):
            list(windows(frame))

    def test_deterministic_regime_boundaries(self):
        self.assertFalse(shock(10, 10))
        self.assertTrue(shock(-10.01, 10))
        self.assertFalse(shock(0, 0))
        self.assertEqual([gap_band(n) for n in [1, 2, 3, 4, 13]], ["1 day", "2-3 days", "2-3 days", "4+ days", "4+ days"])
        for invalid in [0, -1, 1.5, np.nan]:
            with self.assertRaises(ValueError):
                gap_band(invalid)

    def test_selection_comes_from_artifact(self):
        best = pd.DataFrame([{**IDENTITY, "series_id": "example", "baseline": "rolling_median_5", "mae": 91}])
        result = validate_policy(make_policy(best))["series"][0]
        self.assertEqual(result["selected_method"], "rolling_median_5")
        self.assertEqual(result["minimum_history"], 5)
        self.assertEqual(result["benchmark_mae"], 91)

    def test_rolling_and_short_history_fallback(self):
        p = policy()
        self.assertEqual(policy_forecast(p, IDENTITY, history([100, 200]))["prediction"], 200)
        self.assertEqual(policy_forecast(p, IDENTITY, history([100, 200]))["status"], "fallback")
        result = policy_forecast(p, IDENTITY, history(list(range(100, 108))))
        self.assertEqual(result["prediction"], 104)
        self.assertEqual(result["status"], "selected")

    def test_no_zero_or_invented_observation(self):
        for prices in [[], [0, np.nan, -1], [np.inf]]:
            result = policy_forecast(policy(), IDENTITY, history(prices))
            self.assertEqual(result["status"], "insufficient_history")
            self.assertIsNone(result["prediction"])
        result = policy_forecast(policy(), IDENTITY, history([125, 0, np.nan]))
        self.assertEqual(result["prediction"], 125)
        self.assertEqual(result["status"], "fallback")

    def test_exact_identity_and_date_contract(self):
        self.assertEqual(policy_forecast(policy(), {**IDENTITY, "grade": "Other"}, history([100]))["status"], "unrecognized_series")
        mixed = history([100, 200])
        mixed.loc[1, "variety"] = "wrong"
        for bad in [mixed, history([100, 200]).iloc[::-1], pd.concat([history([100]), history([100])])]:
            with self.assertRaises(ValueError):
                policy_forecast(policy(), IDENTITY, bad)

    def test_serialization_and_malformed_policy(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "policy.json"
            path.write_text(json.dumps(policy()), encoding="utf-8")
            self.assertEqual(load_policy(path), policy())
            self.assertEqual(policy_forecast(load_policy(path), IDENTITY, history([100]))["prediction"], 100)
        for key, value in [("window", 8), ("selected_method", "invented"), ("fallback_method", "zero")]:
            bad = policy()
            bad["series"][0][key] = value
            with self.assertRaises(ValueError):
                validate_policy(bad)

    def test_immutability_guard_detects_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "historical.csv"
            path.write_text("original", encoding="utf-8")
            hashes = {str(path): file_digest(path)}
            verify_hashes(hashes)
            path.write_text("changed", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_hashes(hashes)


if __name__ == "__main__":
    unittest.main()
