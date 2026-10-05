"""Small synthetic fixtures used only to verify forecasting invariants."""

from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_baselines import BASELINES, backtest_series, forecast, metrics, score_predictions, run_baselines


def series(values=None, grade="FAQ"):
    values = values if values is not None else list(range(100, 120))
    return pd.DataFrame({"state": "Gujarat", "district": "TEST district", "market": "TEST market",
                         "commodity": "Onion", "variety": "TEST variety", "grade": grade,
                         "date": pd.date_range("2024-01-01", periods=len(values), freq="2D"),
                         "modal_price": values})


class BaselineTests(unittest.TestCase):
    def test_forecast_formulas(self):
        actual = forecast([1, 2, 3, 4, 5, 6, 70])
        self.assertEqual(actual["naive"], 70)
        self.assertEqual(actual["historical_mean"], 13)
        self.assertEqual(actual["historical_median"], 4)
        self.assertEqual(actual["rolling_mean_3"], 27)
        self.assertEqual(actual["rolling_mean_5"], 17.6)
        self.assertEqual(actual["rolling_mean_7"], 13)
        self.assertEqual(actual["rolling_median_5"], 5)

    def test_metrics_and_zero_denominator(self):
        result = metrics([100, 200], [110, 180])
        self.assertEqual(result["mae"], 15)
        self.assertAlmostEqual(result["rmse"], np.sqrt(250))
        self.assertAlmostEqual(result["smape"], 100 * ((20 / 210) + (40 / 380)) / 2)
        self.assertEqual(metrics([0], [0]), {"mae": 0, "rmse": 0, "smape": 0})
        self.assertEqual(metrics([1], [0])["smape"], 200)
        for actual, predicted in [([], []), ([1], [1, 2]), ([float('inf')], [1])]:
            with self.assertRaises(ValueError):
                metrics(actual, predicted)

    def test_chronology_no_filling_and_expanding_history(self):
        frame = series()
        before = frame.copy(deep=True)
        predictions, split = backtest_series(frame.iloc[::-1], "TEST", validation=4, test=4, minimum_history=7)
        self.assertEqual(len(predictions), 8 * len(BASELINES))
        self.assertEqual(predictions.date.nunique(), 8)
        self.assertTrue(predictions.gap_days.eq(2).all())
        self.assertTrue((pd.to_datetime(predictions.previous_observation_date) < pd.to_datetime(predictions.date)).all())
        self.assertEqual(predictions.train_observations.min(), 12)
        self.assertEqual(predictions.train_observations.max(), 19)
        naive = predictions.loc[predictions.baseline.eq("naive")]
        np.testing.assert_array_equal(naive.predicted_modal_price, np.arange(111, 119))
        self.assertEqual(split["test_observations"], 4)
        pd.testing.assert_frame_equal(frame, before)

    def test_future_perturbations_cannot_change_earlier_forecasts(self):
        frame = series()
        original, _ = backtest_series(frame, "TEST", 4, 4, 7)
        for target in range(12, 20):
            changed = frame.copy()
            changed.loc[target:, "modal_price"] = np.arange(9000, 9000 + len(frame) - target)
            updated, _ = backtest_series(changed, "TEST", 4, 4, 7)
            cutoff = frame.iloc[target].date.strftime("%Y-%m-%d")
            a = original.loc[original.date.le(cutoff), ["date", "baseline", "predicted_modal_price"]].reset_index(drop=True)
            b = updated.loc[updated.date.le(cutoff), ["date", "baseline", "predicted_modal_price"]].reset_index(drop=True)
            pd.testing.assert_frame_equal(a, b)

    def test_test_values_do_not_select_model(self):
        frame = series()
        predictions, _ = backtest_series(frame, "TEST", 4, 4, 7)
        _, best, _ = score_predictions(predictions)
        changed = frame.copy()
        changed.loc[16:, "modal_price"] = [9999, 1, 100, 8000]
        updated, _ = backtest_series(changed, "TEST", 4, 4, 7)
        _, updated_best, _ = score_predictions(updated)
        self.assertEqual(best.baseline.tolist(), updated_best.baseline.tolist())
        self.assertEqual(best.validation_mae.tolist(), updated_best.validation_mae.tolist())

    def test_deterministic_ties_and_separate_grades(self):
        first, _ = backtest_series(series([100] * 20), "TEST FAQ", 4, 4, 7)
        second, _ = backtest_series(series([200] * 20, grade="Non-FAQ"), "TEST Non-FAQ", 4, 4, 7)
        all_predictions = pd.concat([first, second], ignore_index=True)
        scores, best, aggregate = score_predictions(all_predictions)
        shuffled = score_predictions(all_predictions.sample(frac=1, random_state=3))
        for a, b in zip((scores, best, aggregate), shuffled):
            pd.testing.assert_frame_equal(a, b)
        self.assertEqual(len(best), 2)
        self.assertEqual(set(best.grade), {"FAQ", "Non-FAQ"})
        self.assertEqual(set(best.baseline), {"historical_mean"})
        self.assertTrue(best.mae.eq(0).all())
        self.assertTrue(best.mae_improvement_over_naive_pct.isna().all())
        with self.assertRaisesRegex(ValueError, "exactly one"):
            backtest_series(pd.concat([series(), series(grade="Non-FAQ")]), "mixed", 4, 4, 7)

    def test_sparse_and_invalid_inputs_fail(self):
        with self.assertRaisesRegex(ValueError, "cannot support"):
            backtest_series(series(), "short")
        for values in ([1, 2], [1, 2, 3, 4, 5, 6, float('nan')], [0] * 7):
            with self.assertRaises(ValueError):
                forecast(values)
        frame = series()
        frame.loc[1, "date"] = frame.loc[0, "date"]
        with self.assertRaisesRegex(ValueError, "unique"):
            backtest_series(frame, "bad", 4, 4, 7)

    def test_changed_benchmark_refuses_overwrite_before_evaluation(self):
        with patch('run_baselines.load_inputs', return_value=(None, None, {})), \
                patch('run_baselines.file_digest', return_value='changed'), \
                patch.object(Path, 'exists', return_value=True), \
                patch.object(Path, 'read_text', return_value='{"benchmark_id":"old"}'), \
                patch('run_baselines.backtest_series') as evaluate:
            with self.assertRaisesRegex(ValueError, "no outputs overwritten"):
                run_baselines()
            evaluate.assert_not_called()


if __name__ == "__main__":
    unittest.main()
