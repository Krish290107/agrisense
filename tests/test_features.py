"""Synthetic in-memory fixtures for causal feature and split invariants only."""

import json
from pathlib import Path
import sys
import unittest

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from build_features import (FEATURES, HISTORICAL_FEATURES, DATE_FEATURES, DEFINITIONS, series_features,
                            build_dataset, verify_evaluation_targets, verify_feature_values)
from market_data_common import SERIES_FIELDS, digest
from run_baselines import backtest_series


def fixture(values=None, **identity_changes):
    values = np.array(values if values is not None else np.arange(100, 120), dtype=float)
    identity = dict(state="Gujarat", district="TEST district", market="TEST market", commodity="Onion",
                    variety="TEST variety", grade="FAQ") | identity_changes
    frame = pd.DataFrame({**identity, "date": pd.date_range("2024-02-20", periods=len(values), freq="2D"),
                          "modal_price": values, "min_price": values - 10, "max_price": values + 20})
    sid = digest(json.dumps(identity, sort_keys=True).encode())[:16]
    return frame, {**identity, "series_id": sid}


def split_fixture(frame, candidate):
    predictions, split = backtest_series(frame, candidate["series_id"], validation=4, test=4, minimum_history=7)
    return predictions, split


class FeatureTests(unittest.TestCase):
    def test_lags_rolling_change_expanding_exclude_extreme_target(self):
        frame, _ = fixture([100, 110, 120, 999, 140, 150, 160, 888])
        result = series_features(frame)
        row = result.iloc[3]
        self.assertEqual(row.modal_price_lag_1, 120)
        self.assertEqual(row.rolling_mean_3, 110)
        self.assertEqual(row.rolling_median_3, 110)
        self.assertEqual(row.rolling_std_3, 10)
        self.assertEqual(row.previous_price_change, 10)
        self.assertAlmostEqual(row.previous_percentage_change, 100 * (120 / 110 - 1))
        self.assertEqual(row.expanding_mean, 110)
        self.assertEqual(row.expanding_median, 110)
        self.assertEqual(row.expanding_std, 10)
        self.assertEqual(row.min_price_lag_1, 110)
        self.assertEqual(row.max_price_lag_1, 140)
        self.assertEqual(row.previous_price_spread, 30)
        self.assertAlmostEqual(result.iloc[7].rolling_mean_7, frame.modal_price.iloc[:7].mean())
        self.assertAlmostEqual(result.iloc[7].rolling_median_7, frame.modal_price.iloc[:7].median())
        self.assertAlmostEqual(result.iloc[7].rolling_std_7, frame.modal_price.iloc[:7].std())
        self.assertEqual(result.iloc[7].rolling_range_7, 899)

    def test_irregular_dates_gap_and_observation_lags_no_filling(self):
        frame, _ = fixture([100, 110, 120, 130, 140, 150, 160, 170])
        frame["date"] = pd.to_datetime(["2024-02-20", "2024-02-21", "2024-02-26", "2024-02-29",
                                       "2024-03-02", "2024-03-03", "2024-03-07", "2024-03-15"])
        result = series_features(frame)
        self.assertEqual(len(result), 8)
        self.assertEqual(result.iloc[-1].modal_price_lag_7, 100)
        self.assertEqual(result.iloc[-1].days_since_previous_observation, 8)
        self.assertAlmostEqual(result.iloc[-1].recent_mean_gap_3, (2 + 1 + 4) / 3)
        self.assertEqual(result.iloc[3].day_of_year, 60)
        self.assertEqual(result.iloc[3].month, 2)
        self.assertEqual(result.iloc[4].quarter, 1)
        self.assertAlmostEqual(result.iloc[4].month_sin, np.sin(2 * np.pi * 2 / 12))

    def test_current_and_future_price_mutation_preserves_predictors(self):
        frame, _ = fixture()
        original = series_features(frame)
        for index in range(len(frame)):
            mutated = frame.copy()
            for column in ["min_price", "modal_price", "max_price"]:
                mutated.loc[index:, column] *= 10
            actual = series_features(mutated)
            pd.testing.assert_frame_equal(original.loc[:index, FEATURES], actual.loc[:index, FEATURES])

    def test_target_timestamp_requires_explicit_availability(self):
        frame, _ = fixture()
        before = series_features(frame)
        frame.loc[len(frame) - 1, "date"] += pd.Timedelta(days=40)
        after = series_features(frame)
        pd.testing.assert_frame_equal(before[HISTORICAL_FEATURES], after[HISTORICAL_FEATURES])
        self.assertNotEqual(before.iloc[-1].days_since_previous_observation, after.iloc[-1].days_since_previous_observation)
        self.assertEqual(len(DATE_FEATURES), 6)
        self.assertTrue(all(item["uses_target_date"] for item in DEFINITIONS if item["name"] in DATE_FEATURES))

    def test_separation_warmup_fixed_splits_and_determinism(self):
        frames, candidates, splits, predictions = [], [], [], []
        variations = [{}, {"district": "SECOND district"}, {"market": "SECOND market"},
                      {"variety": "Other"}, {"grade": "Non-FAQ"}, {"commodity": "Potato"}]
        for i, identity in enumerate(variations):
            frame, candidate = fixture(np.arange(100, 120) + i * 1000, **identity)
            predicted, split = split_fixture(frame, candidate)
            frames.append(frame); candidates.append(candidate); splits.append(split); predictions.append(predicted)
        source, candidate_table, split_table = pd.concat(frames, ignore_index=True), pd.DataFrame(candidates), pd.DataFrame(splits)
        source_before = source.copy(deep=True)
        result, full, summary = build_dataset(source, candidate_table, split_table)
        self.assertEqual(len(full), 120)
        self.assertEqual(len(result), 78)
        self.assertEqual(summary.warmup_rows_removed.sum(), 42)
        self.assertEqual(summary.train_rows.sum(), 30)
        self.assertEqual(summary.validation_rows.sum(), 24)
        self.assertEqual(summary.test_rows.sum(), 24)
        self.assertTrue(full.groupby('series_id').head(1).modal_price_lag_1.isna().all())
        self.assertTrue(result[FEATURES].notna().all().all())
        self.assertEqual(verify_evaluation_targets(result, pd.concat(predictions, ignore_index=True)), 48)
        self.assertEqual(verify_feature_values(source, result), 78)
        for first, repeated in zip((result, full, summary), build_dataset(source.sample(frac=1, random_state=7), candidate_table.iloc[::-1], split_table.iloc[::-1])):
            pd.testing.assert_frame_equal(first, repeated)
        pd.testing.assert_frame_equal(source, source_before)

    def test_early_missing_features_are_not_zero_filled(self):
        frame, _ = fixture([100] * 10)
        result = series_features(frame)
        self.assertTrue(result.iloc[:7].modal_price_lag_7.isna().all())
        self.assertTrue(result.iloc[:3].rolling_std_3.isna().all())
        self.assertTrue(result.iloc[3:].rolling_std_3.eq(0).all())
        self.assertTrue(result.iloc[:2].previous_percentage_change.isna().all())
        self.assertTrue(result.iloc[:4].recent_mean_gap_3.isna().all())

    def test_forbidden_feature_columns_absent(self):
        forbidden = {"modal_price", "min_price", "max_price", "date", "split", "series_id", *SERIES_FIELDS}
        self.assertFalse(forbidden & set(FEATURES))
        self.assertEqual(len(FEATURES), len(set(FEATURES)))
        frame, _ = fixture()
        result = series_features(frame)
        self.assertNotIn("min_price", result.columns)
        self.assertNotIn("max_price", result.columns)
        self.assertEqual(set(HISTORICAL_FEATURES) | set(DATE_FEATURES), set(FEATURES))

    def test_constant_windows_after_volatile_history_have_exact_zero_std(self):
        frame, _ = fixture([150.3, 9999.9, 123.4, 4567.8, 321.9, 7654.3, 246.8] + [2500] * 20)
        result = series_features(frame)
        self.assertTrue(result.iloc[14:].rolling_std_7.eq(0).all())
        for index in range(7, len(frame)):
            self.assertAlmostEqual(result.iloc[index].rolling_std_7, np.std(frame.modal_price.iloc[index-7:index], ddof=1))

    def test_split_tampering_and_evaluation_warmup_fail_clearly(self):
        frame, candidate = fixture()
        predictions, split = split_fixture(frame, candidate)
        altered = split | {"validation_start": "2099-01-01"}
        with self.assertRaisesRegex(ValueError, "boundaries"):
            build_dataset(frame, pd.DataFrame([candidate]), pd.DataFrame([altered]))
        _, short_split = backtest_series(frame, candidate['series_id'], validation=7, test=6, minimum_history=7)
        short_split.update(initial_train_observations=6, initial_train_end=frame.date.iloc[5].strftime('%Y-%m-%d'),
                           validation_observations=8, validation_start=frame.date.iloc[6].strftime('%Y-%m-%d'))
        with self.assertRaisesRegex(ValueError, "lacks required history"):
            build_dataset(frame, pd.DataFrame([candidate]), pd.DataFrame([short_split]))
        result, _, _ = build_dataset(frame, pd.DataFrame([candidate]), pd.DataFrame([split]))
        with self.assertRaises(AssertionError):
            verify_evaluation_targets(result.iloc[:-1], predictions)


if __name__ == "__main__":
    unittest.main()
