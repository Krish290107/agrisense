"""Import canonical artifacts transactionally; never generate production forecasts."""

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from database.store import Repository, IDENTITY, PRICES, json_text, series_id, sha256

OUT = ROOT / "reports/data"


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def csv_rows(path):
    with Path(path).open(encoding="utf-8", newline="") as source:
        return list(csv.DictReader(source))


def verify_hashes(hashes):
    for path, expected in hashes.items():
        if sha256(ROOT / path.replace("\\", "/")) != expected:
            raise ValueError(f"Historical source hash mismatch: {path}")


def import_metadata(repo, directory=OUT, root=ROOT):
    directory, root = Path(directory), Path(root)
    model_path = directory / "model_metadata.json"
    model = read_json(model_path)
    feature_path = directory / "feature_metadata.json"
    feature = read_json(feature_path)
    policy = repo.load_policy()
    if not policy or policy["ml_status"] != "experimental_not_selected":
        raise ValueError("ML status must agree with the frozen policy")
    artifact = model["model_artifact"].replace("\\", "/")
    artifact_path = (root / artifact).resolve()
    if not artifact_path.is_relative_to(root.resolve()):
        raise ValueError("Model artifact must remain inside project root")
    ml_comparison = csv_rows(directory / "ml_baseline_comparison.csv")
    with repo.transaction():
        repo._put("models", {"model_id": model["experiment_id"], "artifact_path": artifact,
                            "artifact_sha256": sha256(artifact_path), "status": policy["ml_status"],
                            "metadata_json": json_text({"schema_version": model["schema_version"], "strategy": model["strategy"],
                                  "feature_schema_sha256": sha256(feature_path), "features": feature["historical_only_feature_names"],
                                  "configurations": [{k: r[k] for k in ["series_id", "config_id", "model", "train_rows", "validation_rows"]} for r in model["selected_configurations"]],
                                  "test_observations": sum(int(r["test_observations"]) for r in ml_comparison),
                                  "source_path": "reports/data/model_metadata.json"})}, ["model_id"])
        sources = [
            (directory / "baseline_metrics.csv", "day5", "baseline", "phase", "evaluation_observations", ""),
            (directory / "ml_baseline_comparison.csv", "day7", "config_id", None, "test_observations", "ml_"),
            (directory / "robustness_window_metrics.csv", "day8-v1", "method", "window", "observations", ""),
        ]
        for path, version, method_field, split_field, count_field, prefix in sources:
            rows = csv_rows(path)
            for row in rows:
                identity = {k: row[k] for k in IDENTITY}
                sid = row["series_id"]
                if sid != series_id(identity) or repo.find_series(identity) is None:
                    raise ValueError("Evaluation references unknown exact identity")
                split = "test" if split_field is None else row[split_field]
                if version.startswith("day8"):
                    split = "historical_test_window_" + split
                key = [version, sid, row[method_field], split]
                evaluation_id = hashlib.sha256(json_text(key).encode()).hexdigest()
                repo._put("evaluations", {"evaluation_id": evaluation_id, "series_id": sid, "version": version,
                          "method": row[method_field], "split": split, "observations": int(row[count_field]),
                          **{metric: float(row[prefix + metric]) for metric in ["mae", "rmse", "smape"]},
                          "notes": "Previously examined historical dates; no pristine holdout claim. Source: " + path.name}, ["evaluation_id"])
            repo.track(path, "evaluation_metrics", len(rows))
        repo.track(model_path, "experimental_model_metadata", 1)
        repo.track(feature_path, "feature_schema", len(feature["historical_only_feature_names"]))


def verify_database(repo, rows, policy):
    expected = {}
    for row in rows:
        sid = series_id({k: row[k] for k in IDENTITY})
        expected.setdefault(sid, []).append(row)
    if repo.summary()["table_counts"]["observations"] != len(rows) or len(expected) != repo.summary()["table_counts"]["series"]:
        raise ValueError("Canonical observation/series counts differ")
    for sid, group in expected.items():
        group.sort(key=lambda row: row["date"])
        actual = repo.get_observations(sid)
        for row, stored in zip(group, actual, strict=True):
            if any(row[k] != stored[k] for k in ["date", *PRICES, "source_sha256"]) or int(row["source_record"]) != stored["source_record"]:
                raise ValueError("Database price/provenance roundtrip differs from canonical CSV")
    if repo.load_policy() != policy:
        raise ValueError("Policy JSON roundtrip differs")
    for entry in policy["series"]:
        sid = entry["series_id"]
        if repo.find_series(entry["identity"])["series_id"] != sid:
            raise ValueError("Policy lookup identity differs")
        stored = repo.get_policy(sid)
        if any(stored[k] != entry[k] for k in ["selected_method", "minimum_history", "window", "fallback_method", "benchmark_mae", "status"]):
            raise ValueError("Normalized database policy differs")
        recent = repo.get_latest_observations(sid, entry["minimum_history"])
        source = expected[sid][-entry["minimum_history"]:]
        if [r["date"] for r in recent] != [r["date"] for r in source] or repo.get_latest_observation(sid) != recent[-1]:
            raise ValueError("Latest-N observation query differs")
    summary = repo.summary()
    if not summary["foreign_keys_enabled"] or summary["foreign_key_violations"] or summary["integrity_check"] != "ok":
        raise ValueError("Database integrity check failed")
    return summary


def run(url=None):
    frozen = read_json(OUT / "robustness_summary.json")
    protected = {**frozen["protected_sha256"], **frozen["output_sha256"],
                 "reports/data/robustness_summary.json": sha256(OUT / "robustness_summary.json")}
    verify_hashes(protected)
    cleaned = ROOT / "data/processed/market_prices_clean.csv"
    policy_path = ROOT / "configs/forecast_policy.json"
    rows, policy = csv_rows(cleaned), read_json(policy_path)
    with Repository(url) as repo:
        repo.initialize()
        with repo.transaction():
            repo.import_observations(cleaned)
            repo.import_policy(policy_path)
            import_metadata(repo)
            first = verify_database(repo, rows, policy)
            repo.import_observations(cleaned)
            repo.import_policy(policy_path)
            import_metadata(repo)
            second = verify_database(repo, rows, policy)
            if first != second:
                raise ValueError("Second import was not idempotent")
            verify_hashes(protected)
        summary = {**second, "engine": "SQLite", "default_database": "data/agrisense.db",
                   "rebuild_status": "verified", "idempotent_second_import": first == second,
                   "first_import_counts": first["table_counts"], "second_import_counts": second["table_counts"],
                   "canonical_price_text_roundtrip": True, "policy_queries_verified": len(policy["series"]),
                   "source_sha256": protected, "implementation_sha256": {p: sha256(ROOT / p) for p in
                    ["database/store.py", "database/schema.sql", "scripts/init_database.py"]}}
    (OUT / "database_summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    counts = summary["table_counts"]
    report = f"""# Day 9 — Database and persistence

Krishkumar | Roll No: 2401CS83 | IIT Patna | https://github.com/Krish290107/agrisense

SQLite schema version 1 uses Python's standard library; no downloads or new dependencies. Default local generated database: `data/agrisense.db`, ignored together with its journal/WAL/SHM files. `DATABASE_URL` accepts local sqlite:/// paths relative to the repository root or an absolute path. Other engines fail explicitly; PostgreSQL is a future adapter, not currently supported. No credentials are stored. A configured alternate path is a trusted local operator setting, not an API parameter.

## Import and verification

- Observations: {counts['observations']}; exact six-field series: {counts['series']}; active policies: {summary['active_policy_series']}.
- Date range: {summary['date_range']['first_date']} through {summary['date_range']['last_date']}.
- Model bundles: {counts['models']}; concise evaluation rows: {counts['evaluations']}; forecast rows: {counts['forecasts']}.
- First and second imports have identical counts and deterministic summaries; duplicate series/date observations: {summary['duplicate_observations']}.
- Every stored observation price string, date and provenance field roundtrips exactly to the cleaned CSV. All nine policy identities, normalized fields, latest and latest-N histories match their source artifacts.
- Foreign keys enabled, foreign-key check empty, integrity check: {summary['integrity_check']}. All protected historical hashes remain unchanged.

## Schema and integrity

`series` enforces exact identity uniqueness. `observations` uses a composite series/date primary key and source SHA/record provenance. `policy_versions` stores the unchanged JSON and active version; `policies` provides normalized per-series lookups. `forecasts` stores future prediction/status, requested identity, timestamp, optional target date, cutoff and policy version. `models` stores experimental bundle paths/hashes and concise feature/configuration metadata, never binary model contents. `evaluations` contains Day 5 metrics, Day 7 comparisons and Day 8 window metrics, not detailed prediction rows. `ingestions` records artifact hashes and logical imported row counts. `schema_info` rejects unknown schema versions.

Price columns are TEXT with decimal validation/comparison CHECK functions registered by the centralized connection helper. This preserves arbitrary source decimal precision, including trailing zeros, without float conversion or silent rounding. Current source prices have at most one decimal place. Query callers receive price strings and can explicitly convert to Decimal for calculations. Direct external writes must register these functions; unsupported writers fail rather than bypass constraints. Aggregate evaluation metrics use REAL, matching existing numeric reports. Dates use canonical ISO YYYY-MM-DD; forecast generation timestamps normalize to UTC with timezone. Date and numeric constraints reject malformed dates, nonfinite prices, nonpositive prices and invalid ordering.

Imports run in nested SQLite savepoints inside one workflow transaction; invalid rows, mismatched identities or changed existing records roll back the entire workflow. Matching records are skipped; conflicting records are never silently replaced. Initial schema creation is separately atomic and idempotent. An empty valid schema may remain after a failed first import. Policy versions are immutable; activating a different version requires an explicit future migration. Rebuilding means running the idempotent importer, not deleting the database. Existing forecast rows survive imports.

Indexes cover exact identities, chronological per-series observations, global observation date ranges, policy lookup, forecast history and per-series evaluation versions. SQL values are parameterized; internal identifiers are allowlisted. Tests use only in-memory/temporary databases.

## Policy and Day 10

Policy methods are imported from the unchanged Day 8 JSON: {json.dumps(summary['policy_methods'])}. Rolling history requirements and naive fallback are preserved. Missing history is represented by an explicit null-valued status, never a zero-price placeholder. ML is `experimental_not_selected`. Forecast storage supports available, fallback, insufficient_history, unsupported_series and error; successful rows require a positive price, matching policy method and a stored history cutoff. Unknown identities can be recorded only as unsupported requests. Target date may be null for next-observed-record forecasts; this avoids inventing a calendar date. No forecasts are generated by this workflow.

Run `python scripts/init_database.py` using the project interpreter. `Repository` provides exact lookup, chronological date-range/latest-N queries (optional as-of cutoff), active policy/config reload, forecast save/read, model and evaluation queries. Connections close via its context manager. The small repository is ready for Day 10 service/API work; frontend, existing API, benchmarks and scientific policy are unchanged. File-backed SQLite is local persistence, not a cloud deployment or concurrent multi-writer production solution. Historical forecasting limitations remain unchanged.
"""
    (OUT / "DATABASE_REPORT.md").write_text(report, encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ["table_counts", "date_range", "policy_methods", "idempotent_second_import"]}, indent=2))
    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", help="Trusted local SQLite URL; defaults to DATABASE_URL or repository data/agrisense.db")
    run(parser.parse_args().database_url)
