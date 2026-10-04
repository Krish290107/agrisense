"""Offline tests using explicitly synthetic, isolated observations only."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from import_market_data import import_file, collect_inputs
from market_data_common import (column_mapping, load_csv, parse_dates, safe_parameters, csv_frames,
                                safe_url)
from profile_market_data import profile_bundles, scope_recommendation, write_reports


class MarketDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="agrisense-synthetic-tests-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.raw = self.base / "raw"
        self.fixture = ROOT / "tests/fixtures/synthetic_mandi.csv"

    def import_fixture(self, path=None, **kwargs):
        settings = dict(raw_root=self.raw, source={"publisher": "SYNTHETIC TEST ONLY"},
                        kind="historical", date_format="%d/%m/%Y")
        settings.update(kwargs)
        return import_file(path or self.fixture, **settings)

    def test_explicit_dates_and_absent_optional_fields(self):
        self.import_fixture()
        report, series, _, files = profile_bundles(self.raw)
        self.assertEqual(report["dates"]["earliest"], "2025-02-01")
        self.assertEqual(report["dates"]["latest"], "2025-02-05")
        self.assertEqual(report["dates"]["parse_failures"], 1)
        self.assertEqual(report["numeric_parse_failures"]["modal_price"], 1)
        self.assertIn("arrivals", files[0]["absent_canonical_fields"])
        self.assertIn("grade", files[0]["absent_canonical_fields"])
        self.assertTrue(all(item["series"]["grade"] is None for item in series))

    def test_ambiguous_dates_are_not_guessed(self):
        frame = load_csv(self.fixture.read_bytes())
        self.assertTrue(parse_dates(frame["Arrival_Date"], None).isna().all())
        parsed = parse_dates(frame["Arrival_Date"], "%m/%d/%Y")
        self.assertEqual(parsed.iloc[0].date().isoformat(), "2025-01-02")

    def test_duplicates_conflicts_order_and_series_gaps(self):
        self.import_fixture()
        report, series, _, _ = profile_bundles(self.raw)
        self.assertEqual(report["exact_duplicate_rows_beyond_first"], 1)
        keys = report["candidate_business_keys"]
        self.assertEqual(keys["repeated_keys"], 1)
        self.assertEqual(keys["rows_beyond_first_per_key"], 2)
        self.assertEqual(keys["conflicting_keys"], 1)
        self.assertEqual(keys["rows_in_conflicting_keys"], 3)
        self.assertEqual(report["price_order_violation_rows"], 1)
        self.assertEqual(report["nonpositive_prices"]["min_price"], 1)
        self.assertEqual(len(series), 3)
        main = next(s for s in series if s["series"]["district"] == "TEST District A" and s["series"]["variety"])
        self.assertEqual(main["observation_days"], 3)
        self.assertEqual(main["calendar_span_days"], 4)
        self.assertEqual(main["missing_calendar_days"], 1)
        self.assertEqual(main["calendar_coverage"], .75)
        self.assertEqual(main["longest_gap_days"], 1)
        self.assertEqual(report["scope_recommendation"]["status"], "pending")

    def test_immutable_content_addressed_import_and_duplicate_skip(self):
        first = self.import_fixture()
        manifest = Path(first["bundle"]) / "provenance.json"
        before = manifest.read_bytes()
        renamed = self.base / "renamed.csv"
        renamed.write_bytes(self.fixture.read_bytes())
        second = self.import_fixture(renamed)
        self.assertEqual(second["status"], "duplicate_skipped")
        self.assertEqual(first["bundle"], second["bundle"])
        self.assertEqual(manifest.read_bytes(), before)
        self.assertEqual((manifest.parent / "source.csv").read_bytes(), self.fixture.read_bytes())
        with self.assertRaisesRegex(ValueError, "another kind"):
            self.import_fixture(kind="snapshots")

    def test_tamper_detection(self):
        result = self.import_fixture()
        path = Path(result["bundle"]) / "source.csv"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "SHA-256"):
            profile_bundles(self.raw)

    def test_existing_raw_originals_and_managed_bundles_are_distinguished(self):
        self.raw.mkdir()
        original = self.raw / "original.csv"
        original.write_bytes(self.fixture.read_bytes())
        bundle = self.import_fixture(original)
        self.assertEqual(collect_inputs(self.raw, self.raw), [original])
        self.assertEqual(collect_inputs(original, self.raw), [original])
        with self.assertRaisesRegex(ValueError, "managed"):
            collect_inputs(Path(bundle["bundle"]) / "source.csv", self.raw)

    def test_streaming_reader_keeps_boundaries_and_rejects_bad_width(self):
        frames = list(csv_frames(self.fixture, chunk_size=2))
        self.assertEqual([len(frame) for frame in frames], [2, 2, 2, 2])
        self.assertEqual(frames[0].iloc[0]["Arrival_Date"], "01/02/2025")
        bad = self.base / "bad.csv"
        bad.write_text("A,B\n1,2\n3,4,5\n")
        with self.assertRaisesRegex(ValueError, "fields"):
            list(csv_frames(bad, chunk_size=1))

    def test_filtered_profile_audits_state_before_filtering_commodities(self):
        self.import_fixture()
        report, _, _, _ = profile_bundles(self.raw, state="Bihar", commodities=["Tomato"])
        self.assertEqual(report["input_row_count"], 8)
        self.assertEqual(report["state_audit"]["rows"], 8)
        self.assertEqual(report["state_audit"]["commodities"]["Potato"]["rows"], 8)
        self.assertEqual(report["row_count"], 0)
        self.assertEqual(report["status"], "no_observations")

    def test_units_missing_conflicting_and_generic_units_unassigned(self):
        self.import_fixture()
        extra = self.base / "unit-conflict.csv"
        extra.write_text("State,District,Market,Commodity,Variety,Date,Min_Price,Max_Price,Modal_Price,Price_Unit,Unit\n"
                         "Bihar,TEST District A,TEST Market,Potato,TEST Variety,2025-02-06,100,200,150,INR/kg,tonne\n", encoding="utf-8")
        self.import_fixture(extra, date_format=None)
        report, _, _, _ = profile_bundles(self.raw)
        self.assertEqual(report["units"]["price"]["missing_rows"], 1)
        self.assertEqual(report["units"]["series_with_conflicting_units"], 1)
        self.assertEqual(report["units"]["generic_unassigned_unit"]["values"], ["tonne"])
        self.assertEqual(report["units"]["quantity"]["count"], 0)

    def test_malformed_csv_and_alias_ambiguity_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "fields"):
            load_csv(b"State,Date\nBihar,2025-01-01,extra\n")
        with self.assertRaisesRegex(ValueError, "unique"):
            load_csv(b"State,State\nBihar,Bihar\n")
        with self.assertRaisesRegex(ValueError, "Multiple columns"):
            column_mapping(["Arrival_Date", "Date"])
        self.assertEqual(column_mapping(["Arrival_Date", "Date"], {"date": "Date"}), {"date": "Date"})

    def test_secret_redaction(self):
        sanitized = safe_url("https://name:secret@example.org/data?api-key=private&token=hidden#sensitive")
        for value in ["name", "secret", "private", "hidden", "sensitive"]:
            self.assertNotIn(value, sanitized)
        result = safe_parameters(["api-key=private", "password=hidden", "custom-secret=x", "state=Gujarat"])
        self.assertEqual(result["api-key"], "[REDACTED]")
        self.assertEqual(result["custom-secret"], "[REDACTED]")
        self.assertEqual(result["state"], "Gujarat")

    def test_pending_report_and_separate_local_samples(self):
        pending, series, samples, files = profile_bundles(self.raw)
        self.assertEqual(pending["status"], "acquisition_pending")
        self.assertIsNone(pending["dates"])
        self.import_fixture()
        result, series, samples, files = profile_bundles(self.raw)
        output = self.base / "reports"
        write_reports(result, series, samples, files, output)
        self.assertEqual(len(json.loads((output / "local/samples.json").read_text())["files"][0]["sample"]), 3)
        self.assertNotIn('"sample":', (output / "data_profile.json").read_text())
        self.assertTrue((output / "local/series_coverage.csv").is_file())
        self.assertTrue((output / "DATA_PROFILE.md").is_file())

    def test_cli_works_from_unrelated_working_directory(self):
        result = subprocess.run([sys.executable, str(ROOT / "scripts/profile_market_data.py"),
                                 "--kind", "snapshots", "--output-dir", str(self.base / "cli-reports")], cwd=self.base,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.base / "cli-reports/data_profile.json").is_file())

    def test_scope_uses_gujarat_and_never_merges_varieties(self):
        # Aggregate records constructed ONLY to exercise the recommendation policy.
        # They are not real coverage and are never written to project reports.
        series = []
        for state in ["Gujarat", "Other TEST State"]:
            for commodity in ["Potato", "Onion", "Tomato"]:
                for market in range(4):
                    for variety in ["TEST A", "TEST B"]:
                        series.append({"series": {"state": state, "district": "TEST", "market": str(market),
                                                  "commodity": commodity, "variety": variety, "grade": "TEST"},
                                       "series_id": f"{state}-{commodity}-{market}-{variety}",
                                       "calendar_span_days": 730, "positive_modal_observation_days": 600,
                                       "calendar_coverage": .82, "longest_gap_days": 5,
                                       "missing_variety_or_grade": False, "price_units": ["INR/quintal"],
                                       "missing_price_unit_rows": 0, "unit_conflict": False,
                                       "invalid_or_missing_date_rows": 0, "nonpositive_price_rows": 0,
                                       "price_order_violation_rows": 0, "incomplete_or_unparseable_price_rows": 0,
                                       "conflicting_key_rows": 0})
        result = scope_recommendation(series, "historical")
        self.assertEqual(result["state"], "Gujarat")
        self.assertEqual(len(result["commodities"]), 3)
        self.assertEqual(len(result["selected_series"]), 12)
        self.assertTrue(all(s["series"]["variety"] == "TEST A" for s in result["selected_series"]))
        self.assertEqual(scope_recommendation(series, "snapshots")["status"], "pending")
        for item in series:
            item["calendar_span_days"] = 650
        shorter = scope_recommendation(series, "historical")
        self.assertEqual(shorter["status"], "provisional_shorter_history")
        self.assertEqual(shorter["strict_target_eligible_series_count"], 0)
        self.assertEqual(shorter["strict_target_minimum_span_days"], 700)
        self.assertEqual(len(shorter["selected_series"]), 12)


if __name__ == "__main__":
    unittest.main()
