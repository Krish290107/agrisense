"""Isolated SQLite tests; never open the persistent project database."""

import csv
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from database.store import Repository, IDENTITY, database_path, series_id
from init_database import import_metadata

IDENTITY_A = dict(zip(IDENTITY, ["Gujarat", "Dahod", "Dahod (Veg. Market)", "Onion", "Onion", "FAQ"]))


def observations(identity=IDENTITY_A, count=9):
    return [{"date": f"2024-01-{i:02d}", **identity, "min_price": "100.000000000000000001",
             "modal_price": f"{100+i}.123456789012345678", "max_price": "200.00", "price_unit": "INR/quintal",
             "source_sha256": "a" * 64, "source_record": str(i)} for i in range(1, count+1)]


def policy(identity=IDENTITY_A):
    return {"schema_version": 1, "evaluation_version": "test-v1", "unit": "INR/quintal", "ml_status": "experimental_not_selected",
            "series": [{"identity": identity, "series_id": series_id(identity), "evaluation_version": "test-v1",
                        "selected_method": "rolling_mean_7", "window": 7, "minimum_history": 7,
                        "fallback_method": "naive", "benchmark_mae": 12.5, "status": "selected"}]}


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.repo = Repository("sqlite:///:memory:")
        self.repo.initialize()
        self.sid = series_id(IDENTITY_A)

    def tearDown(self):
        self.repo.__exit__()
        self.temp.cleanup()

    def csv(self, name, rows):
        path = self.directory / name
        with path.open("w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        return path

    def json(self, name, value):
        path = self.directory / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def seed(self):
        path = self.csv("clean.csv", observations())
        self.repo.import_observations(path)
        self.repo.import_policy(self.json("policy.json", policy()))
        return path

    def test_initialization_configuration_and_schema_version(self):
        self.repo.initialize()
        self.assertEqual(self.repo.summary()["schema_version"], 1)
        self.assertTrue(self.repo.summary()["foreign_keys_enabled"])
        self.assertEqual(database_path("sqlite:///data/example.db"), ROOT / "data/example.db")
        with self.assertRaises(ValueError):
            database_path("postgresql://private")
        self.repo.connection.execute("DELETE FROM schema_info")
        with self.assertRaises(ValueError):
            self.repo.initialize()

    def test_import_idempotency_decimal_roundtrip_and_summary(self):
        source = self.seed()
        before = self.repo.summary()
        self.repo.import_observations(source)
        self.repo.import_policy(self.directory / "policy.json")
        self.assertEqual(self.repo.summary(), before)
        self.assertEqual(before["table_counts"]["series"], 1)
        self.assertEqual(before["table_counts"]["observations"], 9)
        self.assertEqual(self.repo.get_latest_observation(self.sid)["modal_price"], "109.123456789012345678")
        self.assertEqual(self.repo.get_latest_observation(self.sid)["min_price"], "100.000000000000000001")
        self.assertEqual(before["integrity_check"], "ok")

    def test_latest_seven_order_cutoff_and_exact_identity_separation(self):
        identities = [IDENTITY_A, {**IDENTITY_A, "grade": "Non-FAQ"}, {**IDENTITY_A, "variety": "Other"}, {**IDENTITY_A, "market": "Other"}]
        rows = []
        for index, identity in enumerate(identities):
            group = observations(identity)
            for r in group:
                r["modal_price"] = str(120 + index)
            rows.extend(group)
        self.repo.import_observations(self.csv("separate.csv", rows))
        self.repo.import_policy(self.json("policy.json", policy()))
        for index, identity in enumerate(identities):
            sid = self.repo.find_series(identity)["series_id"]
            latest = self.repo.get_latest_observations(sid, 7)
            self.assertEqual([r["date"] for r in latest], [f"2024-01-{i:02d}" for i in range(3, 10)])
            self.assertTrue(all(r["modal_price"] == str(120+index) and r["series_id"] == sid for r in latest))
        self.assertEqual(self.repo.get_latest_observation(self.sid, "2024-01-04")["date"], "2024-01-04")
        self.assertEqual(len(self.repo.get_observations(self.sid, "2024-01-03", "2024-01-05")), 3)
        self.assertIsNone(self.repo.get_latest_observation("unknown"))
        self.assertEqual(self.repo.get_observations("' OR 1=1 --"), [])
        self.assertEqual(self.repo.get_policy(self.sid)["minimum_history"], 7)

    def test_database_unique_keys_and_foreign_keys(self):
        self.seed()
        sql = "INSERT INTO series SELECT ?,state,district,market,commodity,variety,grade,price_unit FROM series WHERE series_id=?"
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute(sql, ("other-id", self.sid))
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute("INSERT INTO observations SELECT * FROM observations LIMIT 1")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute("UPDATE observations SET series_id='missing'")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute("DELETE FROM series WHERE series_id=?", (self.sid,))

    def test_price_date_and_policy_constraints(self):
        self.seed()
        for field, value in [("min_price", "0"), ("modal_price", "-1"), ("max_price", "NaN"),
                             ("modal_price", "Infinity"), ("modal_price", "100.000000000000000000"),
                             ("max_price", "100"), ("date", "2024-02-30")]:
            with self.subTest(field=field, value=value), self.assertRaises(sqlite3.IntegrityError):
                self.repo.connection.execute(f"UPDATE observations SET {field}=?", (value,))
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute("UPDATE policies SET window=NULL")
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.connection.execute("UPDATE policies SET minimum_history=1")

    def test_partial_import_rolls_back_and_conflict_is_not_overwritten(self):
        rows = observations()
        rows[-1]["max_price"] = "0"
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.import_observations(self.csv("invalid.csv", rows))
        self.assertEqual(self.repo.summary()["table_counts"]["series"], 0)
        self.seed()
        before = self.repo.summary()
        changed = observations()
        changed[-1]["modal_price"] = "199"
        with self.assertRaises(ValueError):
            self.repo.import_observations(self.csv("changed.csv", changed))
        self.assertEqual(self.repo.summary(), before)
        self.assertEqual(self.repo.get_latest_observation(self.sid)["modal_price"], observations()[-1]["modal_price"])

    def test_policy_reload_unknown_identity_and_workflow_rollback(self):
        path = self.csv("clean.csv", observations())
        wrong = self.json("bad_policy.json", policy({**IDENTITY_A, "grade": "Unknown"}))
        with self.assertRaises(ValueError), self.repo.transaction():
            self.repo.import_observations(path)
            self.repo.import_policy(wrong)
        self.assertEqual(self.repo.summary()["table_counts"]["observations"], 0)
        self.seed()
        self.assertEqual(self.repo.load_policy(), policy())
        self.assertEqual(len(self.repo.supported_series()), 1)
        before = self.repo.summary()
        with self.assertRaises(ValueError):
            self.repo.import_policy(wrong)
        self.assertEqual(self.repo.summary(), before)

    def test_forecast_save_read_and_null_failure_states(self):
        self.seed()
        args = {"identity": IDENTITY_A, "status": "available", "prediction": "150.123456789012345678",
                "method": "rolling_mean_7", "policy_version": "test-v1", "history_cutoff": "2024-01-09",
                "target_date": None, "generated_at": "2024-01-10T10:00:00+05:30", "forecast_id": "test-forecast"}
        row = self.repo.save_forecast(**args)
        self.assertEqual(row["generated_at"], "2024-01-10T04:30:00+00:00")
        self.assertEqual(row, self.repo.save_forecast(**args))
        self.assertEqual(self.repo.forecast_history(self.sid), [row])
        self.assertEqual(self.repo.get_forecast("test-forecast"), row)
        self.assertEqual(row["prediction"], args["prediction"])
        for state in ["insufficient_history", "error", "unsupported_series"]:
            failed = self.repo.save_forecast(identity=IDENTITY_A, status=state)
            self.assertIsNone(failed["prediction"])
        unknown = self.repo.save_forecast(identity={**IDENTITY_A, "market": "Unknown"}, status="unsupported_series")
        self.assertIsNone(unknown["series_id"])
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.save_forecast(**{**args, "forecast_id": "zero", "prediction": "0"})
        with self.assertRaises(sqlite3.IntegrityError):
            self.repo.save_forecast(identity=IDENTITY_A, status="insufficient_history", prediction="0")
        with self.assertRaises(ValueError):
            self.repo.save_forecast(**{**args, "forecast_id": "wrong-method", "method": "naive"})
        with self.assertRaises(ValueError):
            self.repo.save_forecast(**{**args, "history_cutoff": "2024-01-11"})
        self.repo.import_observations(self.directory / "clean.csv")
        self.assertEqual(self.repo.get_forecast("test-forecast"), row)

    def test_model_and_evaluation_metadata_import_is_idempotent(self):
        self.seed()
        artifact = self.directory / "test.joblib"
        artifact.write_bytes(b"synthetic test artifact, never loaded")
        self.json("feature_metadata.json", {"historical_only_feature_names": ["lag1"]})
        self.json("model_metadata.json", {"schema_version": 1, "experiment_id": "test-model", "model_artifact": "test.joblib",
                  "strategy": "test", "selected_configurations": [{"series_id": self.sid, "config_id": "ridge_1", "model": "Ridge", "train_rows": 10, "validation_rows": 2}]})
        common = {**IDENTITY_A, "series_id": self.sid, "mae": "1", "rmse": "2", "smape": "3"}
        self.csv("baseline_metrics.csv", [{**common, "baseline": "naive", "phase": "test", "evaluation_observations": "2"}])
        self.csv("ml_baseline_comparison.csv", [{**IDENTITY_A, "series_id": self.sid, "config_id": "ridge_1", "test_observations": "2", "ml_mae": "4", "ml_rmse": "5", "ml_smape": "6"}])
        self.csv("robustness_window_metrics.csv", [{**common, "method": "selected_baseline", "window": "1", "observations": "2"}])
        import_metadata(self.repo, self.directory, self.directory)
        before = self.repo.summary()
        import_metadata(self.repo, self.directory, self.directory)
        self.assertEqual(self.repo.summary(), before)
        self.assertEqual(self.repo.get_models()[0]["status"], "experimental_not_selected")
        self.assertEqual(len(self.repo.get_evaluations(self.sid)), 3)
        self.assertEqual(self.repo.get_evaluations("unknown"), [])

    def test_file_database_reopen_and_connection_close(self):
        path = self.directory / "temporary.db"
        url = "sqlite:///" + path.as_posix()
        with Repository(url) as other:
            other.initialize()
            other.import_observations(self.csv("small.csv", observations(count=2)))
        with self.assertRaises(sqlite3.ProgrammingError):
            other.connection.execute("SELECT 1")
        with Repository(url) as reopened:
            reopened.initialize()
            self.assertEqual(len(reopened.get_observations(self.sid)), 2)


if __name__ == "__main__":
    unittest.main()
