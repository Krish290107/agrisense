"""Focused cleaning tests; tiny in-memory observations are test-only."""

import json
from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from clean_market_data import clean_observations, run_cleaning, KEY
from import_market_data import import_file
from market_data_common import column_mapping, file_digest
from profile_market_data import prepare_file


def row(**changes):
    return dict(State="Gujarat", District="Test district", Market="Test market",
                Commodity="Onion", Variety="Test variety", Grade="FAQ",
                Arrival_Date="2024-01-01", Min_Price="100", Modal_Price="150",
                Max_Price="200") | changes


def prepared(rows):
    raw = pd.DataFrame(rows, dtype=str)
    meta = dict(encoding="utf-8", delimiter=",", column_mapping=column_mapping(list(raw.columns)),
                original_headers=list(raw.columns), row_count=len(raw), date_format="%Y-%m-%d",
                price_unit="INR/quintal", sha256="test", kind="historical")
    frame, _, _ = prepare_file(raw, meta, None)
    frame["source_record"] = range(2, len(raw) + 2)
    frame["raw_values"] = [json.dumps(item) for item in rows]
    return frame


class CleaningTests(unittest.TestCase):
    def test_valid_precision_dates_and_safe_normalization(self):
        clean, audit, summary = clean_observations(prepared([
            row(Market="  Test   market ", Min_Price="100.00000000000000001"),
            row(Arrival_Date="2024-01-03")]))
        self.assertEqual(len(clean), 2)
        self.assertTrue(audit.empty)
        self.assertEqual(clean.iloc[0].min_price, "100.00000000000000001")
        self.assertEqual(clean.iloc[0].market, "Test market")
        self.assertEqual(clean.date.tolist(), ["2024-01-01", "2024-01-03"])
        self.assertEqual(summary["observation_dates_after"], 2)

    def test_exact_duplicates(self):
        clean, audit, summary = clean_observations(prepared([row(), row()]))
        self.assertEqual(len(clean), 1)
        self.assertEqual(summary["exact_duplicates_removed"], 1)
        self.assertEqual(audit.iloc[0].rejection_reason, "exact_duplicate")
        self.assertEqual(clean.iloc[0].source_record, 2)

    def test_invalid_values(self):
        for changes, reason in [({"Min_Price": "0"}, "nonpositive_price"),
                                ({"Max_Price": "-1"}, "nonpositive_price"),
                                ({"Modal_Price": "abc"}, "invalid_numeric"),
                                ({"Modal_Price": "NaN"}, "invalid_numeric"),
                                ({"Modal_Price": "inf"}, "invalid_numeric"),
                                ({"Modal_Price": ""}, "invalid_numeric"),
                                ({"Min_Price": "151"}, "invalid_price_order"),
                                ({"Arrival_Date": "2024-02-30"}, "invalid_date"),
                                ({"Arrival_Date": ""}, "invalid_date"),
                                ({"Arrival_Date": "01/02/2024"}, "invalid_date"),
                                ({"Grade": ""}, "missing_identity")]:
            with self.subTest(changes=changes):
                clean, audit, _ = clean_observations(prepared([row(**changes)]))
                self.assertTrue(clean.empty)
                self.assertIn(reason, audit.iloc[0].rejection_reason)

    def test_precise_order_comparison(self):
        clean, audit, _ = clean_observations(prepared([row(Min_Price="150.00000000000000001")]))
        self.assertTrue(clean.empty)
        self.assertIn("invalid_price_order", audit.iloc[0].rejection_reason)

    def test_every_identity_dimension_remains_separate(self):
        rows = [row()] + [row(**{field: value}) for field, value in
                         [("State", "Another state"), ("District", "Another district"),
                          ("Market", "Test market APMC"), ("Commodity", "Potato"),
                          ("Variety", "Other"), ("Grade", "Non-FAQ")]]
        clean, audit, summary = clean_observations(prepared(rows))
        self.assertEqual(summary["series_count_after"], 7)
        self.assertEqual(len(clean), 7)
        self.assertTrue(audit.empty)

    def test_conflicts_include_invalid_siblings(self):
        for price in ("160", "bad"):
            clean, audit, summary = clean_observations(prepared([row(), row(), row(Modal_Price=price)]))
            self.assertTrue(clean.empty)
            self.assertEqual(summary["conflicting_keys"], 1)
            self.assertEqual(summary["rejected_rows"], 3)
            self.assertTrue(audit.rejection_reason.str.contains("conflicting_duplicate_key").all())

    def test_equivalent_keys_and_sort_order(self):
        frame = prepared([row(Arrival_Date="2024-01-03"), row(), row(Market=" Test market ")])
        clean, audit, summary = clean_observations(frame)
        self.assertEqual(summary["equivalent_duplicate_keys_removed"], 1)
        self.assertFalse(clean.duplicated(KEY).any())
        shuffled, shuffled_audit, shuffled_summary = clean_observations(frame.sample(frac=1, random_state=42))
        pd.testing.assert_frame_equal(clean, shuffled)
        pd.testing.assert_frame_equal(audit, shuffled_audit)
        self.assertEqual(summary, shuffled_summary)

    def test_unit_conflict(self):
        clean, audit, _ = clean_observations(prepared([row(Price_Unit="INR/kg")]))
        self.assertTrue(clean.empty)
        self.assertIn("invalid_price_unit", audit.iloc[0].rejection_reason)

    def test_real_entrypoint_idempotency_raw_immutability_schema_and_tamper(self):
        with tempfile.TemporaryDirectory(prefix="agrisense-clean-test-") as directory:
            base = Path(directory)
            source = base / "test.csv"
            pd.DataFrame([row(), row(), row(Arrival_Date="2024-01-02", Max_Price="0")]).to_csv(source, index=False)
            before = file_digest(source)
            imported = import_file(source, raw_root=base / "raw", source={"price_unit": "INR/quintal"},
                                   kind="historical", date_format="%Y-%m-%d")
            bundle = Path(imported["bundle"]) / "source.csv"
            args = (base / "raw", base / "processed", base / "reports")
            first = run_cleaning(*args)
            paths = [base / "processed/market_prices_clean.csv", base / "reports/cleaning_summary.json",
                     base / "reports/local/rejected_rows.csv", base / "reports/CLEANING_REPORT.md"]
            hashes = [file_digest(path) for path in paths]
            self.assertEqual(first, run_cleaning(*args))
            self.assertEqual(hashes, [file_digest(path) for path in paths])
            self.assertEqual(before, file_digest(source))
            self.assertEqual(before, file_digest(bundle))
            with self.assertRaisesRegex(ValueError, "separate from raw"):
                run_cleaning(base / "raw", base / "raw/derived", base / "reports")
            bundle.write_bytes(bundle.read_bytes() + b"\n")
            with self.assertRaisesRegex(ValueError, "SHA-256"):
                run_cleaning(*args)
            self.assertEqual(hashes, [file_digest(path) for path in paths])
            incomplete = base / "incomplete.csv"
            pd.DataFrame([row()]).drop(columns="Grade").to_csv(incomplete, index=False)
            import_file(incomplete, raw_root=base / "incomplete", source={"price_unit": "INR/quintal"}, kind="historical", date_format="%Y-%m-%d")
            with self.assertRaisesRegex(ValueError, "missing required columns: grade"):
                run_cleaning(base / "incomplete", base / "processed", base / "reports")


if __name__ == "__main__":
    unittest.main()
