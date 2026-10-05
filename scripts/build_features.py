"""Causal observation-based features on the immutable Day 5 evaluation regions."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from market_data_common import ROOT, SERIES_FIELDS, PRICES, digest, file_digest, write_json
from run_baselines import load_inputs
from run_eda import label, table

LAGS = (1, 2, 3, 5, 7)
WINDOWS = (3, 7)
WARMUP = 7
CONTEXT_COLUMNS = [*SERIES_FIELDS, "series_id", "date", "split", "modal_price"]


def definitions():
    items = []

    def add(name, family, sources, lookback, description, target_date=False, expanding=False):
        items.append({"name": name, "family": family, "source_columns": sources,
                      "minimum_prior_observations": lookback,
                      "lookback": "all prior observations" if expanding else f"{lookback} prior observations",
                      "uses_target_date": target_date, "description": description,
                      "leakage_safety": ("Known target timestamp plus strictly earlier observations; requires date-known prediction contract."
                                         if target_date else "Computed independently within exact series using only observations strictly before target.")})

    for lag in LAGS:
        add(f"modal_price_lag_{lag}", "lag", ["modal_price"], lag, f"Price {lag} actual observations before target; not a calendar-day lag.")
    for window in WINDOWS:
        for statistic in ("mean", "median", "std"):
            add(f"rolling_{statistic}_{window}", "volatility" if statistic == "std" else "rolling", ["modal_price"], window,
                f"{statistic} of previous {window} observations; shift(1) before rolling, full window required." + (" Sample std, ddof=1." if statistic == "std" else ""))
    add("rolling_range_7", "volatility", ["modal_price"], 7, "Maximum minus minimum of previous seven modal prices.")
    add("previous_price_change", "change", ["modal_price"], 2, "Signed absolute-unit change: price[t-1] minus price[t-2], INR/quintal.")
    add("previous_percentage_change", "change", ["modal_price"], 2, "100 * (price[t-1] / price[t-2] - 1); preceding prices must be positive.")
    for statistic in ("mean", "median", "std"):
        add(f"expanding_{statistic}", "expanding", ["modal_price"], 2 if statistic == "std" else 1,
            f"{statistic} of all strictly preceding modal prices." + (" Sample std, ddof=1." if statistic == "std" else ""), expanding=True)
    for field in ("min_price", "max_price"):
        add(f"{field}_lag_1", "historical_spread", [field], 1, f"Previous observation's {field}; current target-date value is excluded.")
    add("previous_price_spread", "historical_spread", ["min_price", "max_price"], 1, "Previous max_price minus previous min_price, INR/quintal.")
    add("days_since_previous_observation", "timing", ["date"], 1, "Elapsed calendar days from last observed date to known target date; 1 means consecutive dates.", target_date=True)
    add("recent_mean_gap_3", "timing", ["date"], 4, "Mean of last three completed inter-observation intervals, excluding the interval ending at target.")
    for name, description in [("month", "Target-date month, 1–12."), ("quarter", "Target-date quarter, 1–4."),
                              ("day_of_year", "Target-date ordinal day, 1–366; leap years retained."),
                              ("month_sin", "sin(2*pi*(month-1)/12)."), ("month_cos", "cos(2*pi*(month-1)/12).")]:
        add(name, "calendar", ["date"], 0, description, target_date=True)
    return items


DEFINITIONS = definitions()
FEATURES = [item["name"] for item in DEFINITIONS]
HISTORICAL_FEATURES = [item["name"] for item in DEFINITIONS if not item["uses_target_date"]]
DATE_FEATURES = [item["name"] for item in DEFINITIONS if item["uses_target_date"]]


def series_features(group):
    if group.empty or len(group[SERIES_FIELDS].drop_duplicates()) != 1:
        raise ValueError("Features require one nonempty exact series.")
    group = group.copy()
    group["date"] = pd.to_datetime(group.date, errors="raise")
    group = group.sort_values("date", kind="stable").reset_index(drop=True)
    if group.date.isna().any() or group.date.duplicated().any():
        raise ValueError("Series dates must be valid and unique.")
    prices = group[PRICES].apply(pd.to_numeric, errors="raise")
    if (not np.isfinite(prices.to_numpy()).all() or prices.le(0).any().any()
            or prices.min_price.gt(prices.modal_price).any() or prices.modal_price.gt(prices.max_price).any()):
        raise ValueError("Source prices must already pass Day 3 validation.")
    result = group[[*SERIES_FIELDS, "date", "modal_price"]].copy()
    result["modal_price"] = prices.modal_price
    past = prices.modal_price.shift(1)
    for lag in LAGS:
        result[f"modal_price_lag_{lag}"] = prices.modal_price.shift(lag)
    for window in WINDOWS:
        rolling = past.rolling(window, min_periods=window)
        result[f"rolling_mean_{window}"] = rolling.mean()
        result[f"rolling_median_{window}"] = rolling.median()
        # Recompute short-window variance to avoid residual noise on constant windows.
        result[f"rolling_std_{window}"] = rolling.apply(lambda values: np.std(values, ddof=1), raw=True)
    result["rolling_range_7"] = past.rolling(7, min_periods=7).max() - past.rolling(7, min_periods=7).min()
    result["previous_price_change"] = past - prices.modal_price.shift(2)
    result["previous_percentage_change"] = 100 * (past / prices.modal_price.shift(2) - 1)
    result["expanding_mean"] = past.expanding(min_periods=1).mean()
    result["expanding_median"] = past.expanding(min_periods=1).median()
    result["expanding_std"] = past.expanding(min_periods=2).std(ddof=1)
    result["min_price_lag_1"] = prices.min_price.shift(1)
    result["max_price_lag_1"] = prices.max_price.shift(1)
    result["previous_price_spread"] = (prices.max_price - prices.min_price).shift(1)
    gaps = group.date.diff().dt.days
    result["days_since_previous_observation"] = gaps
    result["recent_mean_gap_3"] = gaps.shift(1).rolling(3, min_periods=3).mean()
    result["month"] = group.date.dt.month
    result["quarter"] = group.date.dt.quarter
    result["day_of_year"] = group.date.dt.dayofyear
    result["month_sin"] = np.sin(2 * np.pi * (result.month - 1) / 12)
    result["month_cos"] = np.cos(2 * np.pi * (result.month - 1) / 12)
    return result[[*SERIES_FIELDS, "date", "modal_price", *FEATURES]]


def assign_splits(features, split):
    count_fields = ["initial_train_observations", "validation_observations", "test_observations"]
    sizes = [int(split[field]) for field in count_fields]
    if any(size <= 0 for size in sizes) or sum(sizes) != len(features) or int(split["total_observations"]) != len(features):
        raise ValueError("Day 5 split counts do not match candidate observations.")
    result = features.copy()
    offset = 0
    for region, size, start_field, end_field in [
        ("train", sizes[0], "initial_train_start", "initial_train_end"),
        ("validation", sizes[1], "validation_start", "validation_end"),
        ("test", sizes[2], "test_start", "test_end"),
    ]:
        segment = result.iloc[offset:offset + size]
        if (segment.date.iloc[0] != pd.Timestamp(split[start_field])
                or segment.date.iloc[-1] != pd.Timestamp(split[end_field])):
            raise ValueError(f"Day 5 {region} date boundaries do not match source history.")
        result.loc[result.index[offset:offset + size], "split"] = region
        offset += size
    result["series_id"] = split["series_id"]
    return result[CONTEXT_COLUMNS + FEATURES]


def build_dataset(frame, candidates, splits):
    for name, entries in [("candidates", candidates), ("splits", splits)]:
        if entries.empty or entries.duplicated(SERIES_FIELDS).any() or entries.series_id.duplicated().any():
            raise ValueError(f"Empty or duplicate {name} identities.")
    identity_columns = [*SERIES_FIELDS, "series_id"]
    if set(map(tuple, candidates[identity_columns].to_numpy())) != set(map(tuple, splits[identity_columns].to_numpy())):
        raise ValueError("Day 4 candidates and Day 5 split identities disagree.")
    all_rows, summaries = [], []
    for candidate in candidates.sort_values(SERIES_FIELDS).to_dict("records"):
        identity = {field: candidate[field] for field in SERIES_FIELDS}
        if digest(json.dumps(identity, sort_keys=True).encode())[:16] != candidate["series_id"]:
            raise ValueError("Candidate series ID does not match its full identity.")
        group = frame.loc[(frame[SERIES_FIELDS] == pd.Series(identity)).all(axis=1)]
        split = splits.loc[splits.series_id.eq(candidate["series_id"])].iloc[0]
        features = assign_splits(series_features(group), split)
        unavailable = features[FEATURES].isna().any(axis=1)
        if np.isinf(features[FEATURES].to_numpy(dtype=float)).any():
            raise ValueError("Non-finite engineered values; inspect source prices without filling them.")
        if (unavailable & features.split.ne("train")).any():
            raise ValueError("A Day 5 validation/test target lacks required history; boundaries were not changed.")
        expected = np.arange(len(features)) < WARMUP
        if not np.array_equal(unavailable, expected):
            raise ValueError("Feature availability differs from the seven-observation warm-up policy.")
        usable = features.loc[~unavailable]
        summaries.append({**identity, "series_id": candidate["series_id"], "source_rows": len(features),
                          "warmup_rows_removed": int(unavailable.sum()), "usable_rows": len(usable),
                          **{f"{phase}_rows": int(usable.split.eq(phase).sum()) for phase in ["train", "validation", "test"]}})
        all_rows.append(features)
    full = pd.concat(all_rows, ignore_index=True).sort_values([*SERIES_FIELDS, "date"], kind="stable").reset_index(drop=True)
    usable = full.loc[full[FEATURES].notna().all(axis=1)].reset_index(drop=True)
    return usable, full, pd.DataFrame(summaries)


def verify_evaluation_targets(features, predictions):
    keys = [*SERIES_FIELDS, "series_id", "date", "split"]
    expected = predictions.rename(columns={"phase": "split", "actual_modal_price": "modal_price"}).copy()
    expected["date"] = pd.to_datetime(expected.date)
    expected = expected[[*keys, "modal_price"]].drop_duplicates().sort_values(keys).reset_index(drop=True)
    actual = features.loc[features.split.isin(["validation", "test"]), [*keys, "modal_price"]].sort_values(keys).reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected, check_dtype=False, check_exact=True)
    return len(actual)


def verify_feature_values(frame, features):
    """Independent array-prefix reconstruction, including known-date exceptions."""
    checked = 0
    for identity, rows in features.groupby(SERIES_FIELDS, sort=True):
        source = frame.loc[(frame[SERIES_FIELDS] == identity).all(axis=1)].sort_values("date").reset_index(drop=True)
        positions = {date: i for i, date in enumerate(source.date)}
        for row in rows.itertuples(index=False):
            index = positions[row.date]
            past = source.modal_price.iloc[:index].to_numpy(dtype=float)
            values = {f"modal_price_lag_{lag}": past[-lag] for lag in LAGS}
            for window in WINDOWS:
                sample = past[-window:]
                values.update({f"rolling_mean_{window}": np.mean(sample), f"rolling_median_{window}": np.median(sample),
                               f"rolling_std_{window}": np.std(sample, ddof=1)})
            previous = source.iloc[index - 1]
            prior_dates = source.date.iloc[:index]
            gaps = np.diff(prior_dates.to_numpy()).astype("timedelta64[D]").astype(int)
            month = row.date.month
            values.update({"rolling_range_7": np.ptp(past[-7:]), "previous_price_change": past[-1] - past[-2],
                           "previous_percentage_change": 100 * (past[-1] / past[-2] - 1),
                           "expanding_mean": np.mean(past), "expanding_median": np.median(past), "expanding_std": np.std(past, ddof=1),
                           "min_price_lag_1": previous.min_price, "max_price_lag_1": previous.max_price,
                           "previous_price_spread": previous.max_price - previous.min_price,
                           "days_since_previous_observation": (row.date - previous.date).days,
                           "recent_mean_gap_3": np.mean(gaps[-3:]), "month": month, "quarter": row.date.quarter,
                           "day_of_year": row.date.dayofyear, "month_sin": np.sin(2 * np.pi * (month - 1) / 12),
                           "month_cos": np.cos(2 * np.pi * (month - 1) / 12)})
            np.testing.assert_allclose([getattr(row, name) for name in FEATURES], [values[name] for name in FEATURES], rtol=1e-10, atol=1e-8)
            checked += 1
    return checked


def protected_inputs():
    summary_path = ROOT / "reports/data/baseline_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if digest(json.dumps(summary["reproducibility"], sort_keys=True).encode()) != summary["benchmark_id"]:
        raise ValueError("Day 5 benchmark identity is invalid.")
    expected = {**summary["reproducibility"]["inputs"], **summary["reproducibility"]["code"], **summary["artifact_sha256"]}
    for relative, checksum in expected.items():
        if file_digest(ROOT / relative) != checksum:
            raise ValueError(f"Protected Day 5 dependency/artifact changed: {relative}; restore/verify the benchmark first.")
    expected[str(summary_path.relative_to(ROOT))] = file_digest(summary_path)
    return summary, expected


def make_report(summary, series_summary):
    rows = [{"Series (Gujarat)": label(row), "Source": row["source_rows"], "Warm-up": row["warmup_rows_removed"],
             "Train": row["train_rows"], "Validation": row["validation_rows"], "Test": row["test_rows"]}
            for row in series_summary.to_dict("records")]
    return "\n\n".join([
        "# Day 6: historical time-series feature engineering",
        "Krishkumar | 2401CS83 | IIT Patna\n\nRepository: https://github.com/Krish290107/agrisense",
        "## Dataset and split preservation",
        f"{summary['candidate_series']} exact series; {summary['source_rows']:,} source observations produce {summary['usable_rows']:,} ML rows with {len(FEATURES)} numeric features. Removed {summary['warmup_rows_removed']} early training rows only (seven per series). Train/validation/test counts: {summary['rows_by_split']['train']:,} / {summary['rows_by_split']['validation']:,} / {summary['rows_by_split']['test']:,}. All Day 5 validation/test identities, dates and target prices are preserved exactly.",
        table(rows, ["Series (Gujarat)", "Source", "Warm-up", "Train", "Validation", "Test"]),
        "Source data, candidate readiness and the fixed Day 5 benchmark are hash-checked, never rewritten. The canonical output is `data/processed/forecast_features.csv`, sorted by six-field identity and date. `split` retains the Day 5 regions; `modal_price` is the output target, not an input feature. Use the explicit lists in [feature_metadata.json](feature_metadata.json), never all numeric columns by default. Identity categories stay unencoded. Same-row min_price/max_price are absent.",
        "## Definitions and availability",
        table([{"Family": family, "Features": ", ".join(item["name"] for item in DEFINITIONS if item["family"] == family)} for family in summary["features_by_family"]], ["Family", "Features"]),
        "Lags count prior actual observations: lag_7 need not mean seven calendar days. Rolling means, medians, sample standard deviations (ddof=1) and ranges operate on shift(1) history, requiring complete windows. Expanding statistics use all strictly earlier observations. Signed price change is price[t-1] minus price[t-2]; percentage change is 100 times their ratio minus one. Historical min/max/spread use t-1 only. Constant-history volatility may legitimately be zero; unavailable volatility is never zero-filled.",
        "No missing calendar rows, interpolated prices or imputed feature history are created. All excluded rows are the expected initial seven observations of each series. Missing counts before and after warm-up removal are recorded in feature_summary.json; retained features have no missing or infinite values. The largest finite lookback is seven observations; expanding features require the entire available prefix. Historical mean gap uses the last three completed intervals (four prior observations), excluding the target interval.",
        "## Target-date information contract",
        f"The requested Day 6 design assumes the prediction date is known before predicting its price. Six conditional features use that date: {', '.join(DATE_FEATURES)}. No current/future price is used. Calendar fields include leap-year day-of-year and deterministic month sine/cosine; these are representations, not claims of established seasonality.",
        f"Day 5 forecast the next observed record without knowing its eventual date. To match that information set strictly, use the {len(HISTORICAL_FEATURES)} `historical_only_feature_names`. The full {len(FEATURES)}-feature list is valid only for a date-known scenario and must be labeled as additional information in Day 7 comparisons. Dates of future market reports are not guaranteed known operationally; this dataset does not establish that availability. Target-date gaps are elapsed days (1 means consecutive dates), not missing-day counts.",
        "## Leakage checks and Day 7 use",
        f"The real pipeline independently reconstructs every retained feature from array prefixes ({summary['leakage_validation']['rows_checked']:,} rows) and compares all feature values. It also checks all {summary['leakage_validation']['evaluation_targets_preserved']} validation/test targets against immutable Day 5 forecast records. Unit tests mutate current/future modal/min/max prices and verify that earlier/current-row predictors do not change; exact series remain isolated.",
        "Precomputing these causal features is consistent with Day 5 walk-forward evaluation: after a validation/test outcome is observed it can enter the next row's history. It is not a simultaneous multi-step forecast of the whole holdout. Model fitting, scaling, imputation (if later needed), encoding and selection must use training history only, with validation tuning and final test scoring. The 63 warm-up observations can supply lag context but cannot be supervised training rows; retain the same validation/test dates and disclose that ML training has fewer usable rows than baseline history.",
        "No model was trained, no feature was selected using test scores/correlations, and no diagnostic target correlations were computed. Day 4 selected the cohort retrospectively; limited history, irregular reporting, stale endpoints and unknown publication/revision timestamps still limit generalization. Availability of preceding prices is assumed from recorded observation dates, including lagged min/max. Production use must verify publication timing.",
        "## Reproduction",
        "Run `.\\.venv\\Scripts\\python.exe scripts/build_features.py`. Outputs: canonical feature CSV, feature_metadata.json, feature_summary.json, feature_series_summary.csv and this report. Inputs, code and output hashes support audit and deterministic reruns. No new dependencies or downloads are required.",
        "Day 7: train and compare ML models against the immutable Day 5 benchmarks, with explicit information-availability rules and the unchanged chronological targets.",
    ]) + "\n"


def run_features():
    benchmark, protected = protected_inputs()
    frame, candidates, _ = load_inputs()
    splits = pd.read_csv(ROOT / "reports/data/baseline_splits.csv", keep_default_na=False)
    predictions = pd.read_csv(ROOT / "reports/data/local/baseline_predictions.csv", keep_default_na=False)
    usable, full, series_summary = build_dataset(frame, candidates, splits)
    targets = verify_evaluation_targets(usable, predictions)
    checked = verify_feature_values(frame, usable)
    if not np.isfinite(usable[FEATURES].to_numpy()).all():
        raise ValueError("Retained feature matrix is incomplete or non-finite.")
    families = {family: [item["name"] for item in DEFINITIONS if item["family"] == family]
                for family in dict.fromkeys(item["family"] for item in DEFINITIONS)}
    metadata = {"schema_version": 1, "target": "modal_price", "target_unit": "INR/quintal",
                "identity_columns": SERIES_FIELDS, "context_columns_not_features": CONTEXT_COLUMNS,
                "feature_names": FEATURES, "historical_only_feature_names": HISTORICAL_FEATURES,
                "requires_known_target_date": DATE_FEATURES,
                "availability_contract": "Full feature list assumes target date known; historical-only list does not. All prices are strictly earlier within exact series.",
                "features": DEFINITIONS}
    summary = {"schema_version": 1, "candidate_series": len(candidates), "source_rows": len(full),
               "usable_rows": len(usable), "feature_count": len(FEATURES), "historical_only_feature_count": len(HISTORICAL_FEATURES),
               "warmup_rows_removed": len(full) - len(usable), "warmup_prior_observations": WARMUP,
               "rows_by_split": {phase: int(usable.split.eq(phase).sum()) for phase in ["train", "validation", "test"]},
               "features_by_family": families,
               "missing_before_warmup_removal": {name: int(full[name].isna().sum()) for name in FEATURES},
               "missing_after_warmup_removal": {name: int(usable[name].isna().sum()) for name in FEATURES},
               "leakage_validation": {"status": "passed", "method": "Independent array-prefix reconstruction of every retained feature; known-date features explicitly conditional",
                                      "rows_checked": checked, "evaluation_targets_preserved": targets},
               "baseline_benchmark_id": benchmark["benchmark_id"], "protected_inputs_sha256": protected,
               "feature_code_sha256": file_digest(Path(__file__)), "software": {"pandas": pd.__version__, "numpy": np.__version__}}
    for relative, checksum in protected.items():
        if file_digest(ROOT / relative) != checksum:
            raise ValueError("Protected input changed during feature engineering; no outputs written.")
    output = ROOT / "reports/data"
    dataset_path = ROOT / "data/processed/forecast_features.csv"
    usable.to_csv(dataset_path, index=False, date_format="%Y-%m-%d", lineterminator="\n", float_format="%.15g")
    series_summary.to_csv(output / "feature_series_summary.csv", index=False, lineterminator="\n")
    write_json(output / "feature_metadata.json", metadata)
    (output / "FEATURE_ENGINEERING_REPORT.md").write_text(make_report(summary, series_summary), encoding="utf-8", newline="\n")
    summary["output_sha256"] = {str(path.relative_to(ROOT)): file_digest(path) for path in
                                [dataset_path, output / "feature_series_summary.csv", output / "feature_metadata.json", output / "FEATURE_ENGINEERING_REPORT.md"]}
    write_json(output / "feature_summary.json", summary)
    print(f"Processed {len(candidates)} series, {len(full):,} observations -> {len(usable):,} rows, {len(FEATURES)} features; warm-up removed {len(full)-len(usable)}.")
    print(f"Splits: {summary['rows_by_split']}; prefix verification passed for {checked:,} rows; {targets} Day 5 targets preserved.")
    print("Dataset: data/processed/forecast_features.csv; report: reports/data/FEATURE_ENGINEERING_REPORT.md")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        run_features()
    except (ValueError, OSError, KeyError, AssertionError) as exc:
        print(f"Feature engineering failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
