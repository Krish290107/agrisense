"""Tiny in-memory analytical fixtures, never included in project data/reports."""

from pathlib import Path
import sys
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from run_eda import analyze, readiness, validate_dataset
from market_data_common import SERIES_FIELDS


def observations():
    return pd.DataFrame([
        {"date": day, "state": "Gujarat", "district": "Test district", "market": "Test market",
         "commodity": commodity, "variety": "Test variety", "grade": "FAQ", "min_price": "100",
         "modal_price": "150", "max_price": "200", "price_unit": "INR/quintal",
         "source_sha256": "test-only", "source_record": str(index + 2)}
        for index, (commodity, day) in enumerate([
            ("Onion", "2024-01-01"), ("Onion", "2024-01-04"), ("Onion", "2024-01-06"),
            ("Potato", "2024-01-06"), ("Tomato", "2024-01-06")])])


class EdaTests(unittest.TestCase):
    def test_coverage_gaps_and_no_filling(self):
        frame = validate_dataset(observations())
        before = frame.copy(deep=True)
        output = analyze(frame)
        series = output[1]
        onion = series.loc[series.commodity.eq("Onion")].iloc[0]
        self.assertEqual(onion.observation_count, 3)
        self.assertEqual(onion.span_days, 6)
        self.assertEqual(onion.coverage_ratio, .5)
        self.assertEqual(onion.max_gap_days, 2)
        self.assertEqual(onion.median_gap_days, 1.5)
        singleton = series.loc[series.commodity.eq("Potato")].iloc[0]
        self.assertEqual(singleton.max_gap_days, 0)
        self.assertTrue(pd.isna(singleton.median_gap_days))
        self.assertEqual(singleton.readiness_status, "insufficient")
        self.assertEqual(len(output[0]), len(frame))
        pd.testing.assert_frame_equal(frame, before)

    def test_threshold_boundaries_and_staleness(self):
        item = dict(observation_count=365, span_days=600, coverage_ratio=.5, max_gap_days=45, recency_days=60)
        self.assertEqual(readiness(item)[0], "eligible")
        for key, value in [("observation_count", 364), ("span_days", 599), ("coverage_ratio", .49),
                           ("max_gap_days", 46), ("recency_days", 61)]:
            self.assertEqual(readiness(item | {key: value})[0], "limited")
        self.assertEqual(readiness(item | {"recency_days": 181})[0], "insufficient")
        self.assertEqual(readiness(item | {"observation_count": 89})[0], "insufficient")

    def test_integrity_errors_do_not_clean(self):
        for change in [{"date": "2024-02-30"}, {"modal_price": "0"}, {"min_price": "151"},
                       {"max_price": "inf"}, {"grade": ""}, {"price_unit": "INR/kg"}, {"state": "Other"}]:
            frame = observations()
            for key, value in change.items():
                frame.loc[0, key] = value
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_dataset(frame)
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            frame = observations()
            validate_dataset(pd.concat([frame, frame.iloc[[0]]], ignore_index=True))
        with self.assertRaisesRegex(ValueError, "missing columns"):
            validate_dataset(observations().drop(columns="grade"))

    def test_identity_and_deterministic_analysis(self):
        frame = observations()
        extra = []
        for field, value in [("district", "Another district"), ("market", "Test market APMC"),
                             ("variety", "Other"), ("grade", "Non-FAQ")]:
            extra.append(frame.iloc[0].to_dict() | {field: value})
        frame = pd.concat([frame, pd.DataFrame(extra)], ignore_index=True)
        first = analyze(validate_dataset(frame))
        second = analyze(validate_dataset(frame.sample(frac=1, random_state=1)))
        self.assertEqual(first[-1], second[-1])
        for a, b in zip(first[:-1], second[:-1]):
            pd.testing.assert_frame_equal(a, b)
        self.assertEqual(len(first[1]), 7)
        self.assertEqual(len(first[1][SERIES_FIELDS].drop_duplicates()), 7)

    def test_outlier_screen_does_not_delete_spikes(self):
        base = observations()
        template = base.iloc[0].to_dict()
        rows = []
        for i, day in enumerate(pd.date_range("2024-01-01", periods=40)):
            value = 10000 if i == 39 else 100 + i
            rows.append(template | {"date": day.strftime("%Y-%m-%d"), "min_price": "1",
                                    "modal_price": str(value), "max_price": "12000"})
        frame = pd.concat([base.loc[base.commodity.ne("Onion")], pd.DataFrame(rows)], ignore_index=True)
        output = analyze(validate_dataset(frame))
        self.assertEqual(len(output[0]), 42)
        self.assertEqual(len(output[-2]), 1)
        self.assertEqual(output[-1]["outliers"]["screened_series"], 1)
        self.assertEqual(output[-1]["outliers"]["unscreened_series"], 2)
        self.assertEqual(output[-2].iloc[0].modal_price, 10000)


if __name__ == "__main__":
    unittest.main()
