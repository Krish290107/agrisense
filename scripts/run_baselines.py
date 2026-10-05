"""Univariate next-observation benchmarks with chronological model selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from market_data_common import ROOT, SERIES_FIELDS, digest, file_digest, write_json
from run_eda import COLORS, label, table, validate_dataset

BASELINES = ["naive", "historical_mean", "historical_median", "rolling_mean_3",
             "rolling_mean_5", "rolling_mean_7", "rolling_median_5"]
POLICY = {"minimum_initial_history": 365, "validation_observations": 60, "test_observations": 60,
          "horizon": "next observed record, not next calendar day",
          "selection": "validation MAE, then validation RMSE, then baseline name; frozen before test",
          "update": "expanding history; reveal each actual only after predicting it"}
FIGURES = ["01_naive_reference.png", "02_onion_selected.png", "03_potato_selected.png",
           "04_tomato_selected.png", "05_model_mae.png", "06_selected_baselines.png",
           "07_error_distributions.png", "08_error_by_gap.png"]
TABLES = ["baseline_metrics.csv", "best_baselines.csv", "baseline_aggregate.csv", "baseline_splits.csv",
          "baseline_gap_errors.csv", "baseline_error_examples.csv"]


def forecast(history):
    values = np.asarray(history, dtype=float)
    if values.ndim != 1 or len(values) < 7 or not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Baselines require at least seven finite positive past observations.")
    return {"naive": float(values[-1]), "historical_mean": float(np.mean(values)),
            "historical_median": float(np.median(values)), "rolling_mean_3": float(np.mean(values[-3:])),
            "rolling_mean_5": float(np.mean(values[-5:])), "rolling_mean_7": float(np.mean(values[-7:])),
            "rolling_median_5": float(np.median(values[-5:]))}


def metrics(actual, predicted):
    actual, predicted = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if actual.ndim != 1 or not len(actual) or actual.shape != predicted.shape:
        raise ValueError("Metrics require nonempty equally sized forecast/actual vectors.")
    if not np.isfinite(actual).all() or not np.isfinite(predicted).all():
        raise ValueError("Metrics require finite forecast/actual pairs.")
    errors = predicted - actual
    denominator = np.abs(actual) + np.abs(predicted)
    ratios = np.divide(2 * np.abs(errors), denominator, out=np.zeros_like(errors), where=denominator != 0)
    return {"mae": float(np.mean(np.abs(errors))), "rmse": float(np.sqrt(np.mean(errors ** 2))),
            "smape": float(100 * np.mean(ratios))}


def backtest_series(group, series_id, validation=60, test=60, minimum_history=365):
    if validation < 1 or test < 1 or minimum_history < 7:
        raise ValueError("Evaluation periods must be positive and minimum history at least seven.")
    if group[SERIES_FIELDS].drop_duplicates().shape[0] != 1:
        raise ValueError("Backtest requires exactly one six-field series identity.")
    group = group.sort_values("date", kind="stable").reset_index(drop=True)
    dates = pd.to_datetime(group.date, errors="raise")
    if dates.isna().any() or dates.duplicated().any():
        raise ValueError("Backtest observation dates must be valid and unique.")
    values = group.modal_price.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise ValueError("Backtest targets must be finite positive prices.")
    initial = len(group) - validation - test
    if initial < minimum_history:
        raise ValueError(f"Series {series_id}: {len(group)} observations cannot support {minimum_history} initial + {validation} validation + {test} test.")
    identity = {field: str(group.iloc[0][field]) for field in SERIES_FIELDS}
    rows = []
    for target_index in range(initial, len(group)):
        # The target and all later observations are excluded from this model input.
        predictions = forecast(values[:target_index])
        for baseline in BASELINES:
            prediction, actual = predictions[baseline], float(values[target_index])
            rows.append({**identity, "series_id": series_id,
                         "phase": "validation" if target_index < initial + validation else "test",
                         "date": dates.iloc[target_index].date().isoformat(),
                         "actual_modal_price": actual, "predicted_modal_price": prediction, "baseline": baseline,
                         "absolute_error": abs(prediction - actual), "squared_error": (prediction - actual) ** 2,
                         "previous_observation_date": dates.iloc[target_index - 1].date().isoformat(),
                         "gap_days": int((dates.iloc[target_index] - dates.iloc[target_index - 1]).days),
                         "train_observations": target_index,
                         "target_observation_index": target_index + 1})
    split = {**identity, "series_id": series_id, "total_observations": len(group),
             "initial_train_observations": initial, "initial_train_start": dates.iloc[0].date().isoformat(),
             "initial_train_end": dates.iloc[initial - 1].date().isoformat(),
             "validation_start": dates.iloc[initial].date().isoformat(),
             "validation_end": dates.iloc[initial + validation - 1].date().isoformat(),
             "validation_observations": validation, "test_start": dates.iloc[initial + validation].date().isoformat(),
             "test_end": dates.iloc[-1].date().isoformat(), "test_observations": test}
    return pd.DataFrame(rows), split


def score_predictions(predictions):
    records = []
    keys = [*SERIES_FIELDS, "series_id", "phase", "baseline"]
    for identity, group in predictions.groupby(keys, sort=True):
        records.append(dict(zip(keys, identity)) | {
            "train_observations": int(group.train_observations.min()),
            "last_train_observations": int(group.train_observations.max()),
            "evaluation_observations": len(group), "evaluation_start": group.date.min(),
            "evaluation_end": group.date.max(), **metrics(group.actual_modal_price, group.predicted_modal_price)})
    scores = pd.DataFrame(records).sort_values([*SERIES_FIELDS, "phase", "mae", "rmse", "baseline"], kind="stable")
    scores["rank"] = scores.groupby(["series_id", "phase"], sort=False).cumcount() + 1
    scores["is_phase_best"] = scores["rank"].eq(1)
    scores["is_phase_worst"] = scores["rank"].eq(len(BASELINES))
    selected = scores.loc[scores.phase.eq("validation") & scores["rank"].eq(1)]
    chosen = dict(zip(selected.series_id, selected.baseline))
    scores["selected_on_validation"] = [chosen[sid] == model for sid, model in zip(scores.series_id, scores.baseline)]
    best = scores.loc[scores.phase.eq("test") & scores.selected_on_validation].copy()
    validation_scores = selected.set_index("series_id")
    best["validation_mae"] = best.series_id.map(validation_scores.mae)
    best["validation_rmse"] = best.series_id.map(validation_scores.rmse)
    naive = scores.loc[scores.phase.eq("test") & scores.baseline.eq("naive")].set_index("series_id")
    best["naive_test_mae"] = best.series_id.map(naive.mae)
    best["mae_improvement_over_naive_pct"] = 100 * (1 - best.mae / best.naive_test_mae.replace(0, np.nan))
    best = best.sort_values(["commodity", *SERIES_FIELDS], kind="stable").reset_index(drop=True)
    aggregate = []
    for (phase, baseline), group in scores.groupby(["phase", "baseline"], sort=True):
        aggregate.append({"phase": phase, "baseline": baseline, "series": len(group),
                          "mean_mae": float(group.mae.mean()), "median_mae": float(group.mae.median()),
                          "median_rmse": float(group.rmse.median()), "mean_smape": float(group.smape.mean()),
                          "phase_wins": int(group["rank"].eq(1).sum()),
                          "validation_selections": int(group.selected_on_validation.sum())})
    return scores.reset_index(drop=True), best, pd.DataFrame(aggregate)


def analyze_errors(predictions, best):
    selected = dict(zip(best.series_id, best.baseline))
    test = predictions.loc[predictions.phase.eq("test")].copy()
    test["gap_band"] = pd.cut(test.gap_days, [0, 1, 3, 7, np.inf], labels=["1", "2–3", "4–7", "8+"]).astype(str)
    chosen = test.loc[[selected[sid] == baseline for sid, baseline in zip(test.series_id, test.baseline)]].copy()
    naive = test.loc[test.baseline.eq("naive")].copy()
    gap_rows = []
    for policy, frame in [("validation_selected", chosen), ("naive", naive)]:
        for (commodity, band), group in frame.groupby(["commodity", "gap_band"], sort=True):
            gap_rows.append({"policy": policy, "commodity": commodity, "gap_band_days": band,
                             "comparisons": len(group), **metrics(group.actual_modal_price, group.predicted_modal_price)})
    examples = chosen.sort_values(["series_id", "absolute_error", "date"], ascending=[True, False, True]).groupby("series_id", sort=True).head(3)
    previous = naive.set_index(["series_id", "date"])["predicted_modal_price"]
    examples = examples.copy()
    examples["previous_modal_price"] = [previous.loc[(sid, date)] for sid, date in zip(examples.series_id, examples.date)]
    examples["observed_price_change_pct"] = 100 * (examples.actual_modal_price / examples.previous_modal_price - 1)
    return chosen, naive, pd.DataFrame(gap_rows), examples


def load_inputs(data_dir=ROOT / "reports/data", cleaned=ROOT / "data/processed/market_prices_clean.csv"):
    paths = [cleaned, data_dir / "cleaning_summary.json", data_dir / "eda_summary.json",
             data_dir / "forecast_candidates.csv", data_dir / "series_readiness.csv"]
    hashes = {str(path.relative_to(ROOT)): file_digest(path) for path in paths}
    cleaning = json.loads(paths[1].read_text(encoding="utf-8"))
    eda = json.loads(paths[2].read_text(encoding="utf-8"))
    if hashes[str(cleaned.relative_to(ROOT))] != cleaning["cleaned_sha256"] or cleaning["cleaned_sha256"] != eda["input_sha256"]:
        raise ValueError("Cleaned-data hash disagrees with Day 3/4 provenance.")
    frame = validate_dataset(pd.read_csv(cleaned, dtype=str, keep_default_na=False))
    candidates = pd.read_csv(paths[3], dtype=str, keep_default_na=False)
    readiness = pd.read_csv(paths[4], dtype=str, keep_default_na=False)
    for name, table_data in [("candidate", candidates), ("readiness", readiness)]:
        if table_data.empty or not {*SERIES_FIELDS, "series_id", "readiness_status"}.issubset(table_data.columns):
            raise ValueError(f"Missing/invalid {name} table schema.")
        if table_data.duplicated(SERIES_FIELDS).any() or table_data.series_id.duplicated().any():
            raise ValueError(f"Duplicate identities in {name} table.")
    if len(frame) != cleaning["output_rows"] or len(frame[SERIES_FIELDS].drop_duplicates()) != cleaning["series_count_after"]:
        raise ValueError("Cleaned-data counts disagree with provenance.")
    expected = {tuple(row[field] for field in SERIES_FIELDS) for row in eda["selected_candidates"]}
    if set(map(tuple, candidates[SERIES_FIELDS].to_numpy())) != expected:
        raise ValueError("Candidate table disagrees with Day 4 summary; regenerate/verify Day 4.")
    for row in candidates.to_dict("records"):
        identity = {field: row[field] for field in SERIES_FIELDS}
        sid = digest(json.dumps(identity, sort_keys=True).encode())[:16]
        reference = readiness.loc[readiness.series_id.eq(sid)]
        group = frame.loc[(frame[SERIES_FIELDS] == pd.Series(identity)).all(axis=1)]
        if (sid != row["series_id"] or row["readiness_status"] != "eligible" or len(reference) != 1
                or reference.iloc[0][SERIES_FIELDS].to_dict() != identity
                or reference.iloc[0].readiness_status != "eligible"
                or len(group) != int(row["observation_count"])
                or len(group) != int(reference.iloc[0].observation_count)):
            raise ValueError("Candidate identity/readiness/count does not match cleaned observations.")
    return frame, candidates.sort_values(["commodity", *SERIES_FIELDS], kind="stable"), hashes


def make_figures(predictions, best, aggregate, selected, naive, output):
    output.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.alpha": .18,
                         "figure.facecolor": "white", "savefig.facecolor": "white"})
    representatives = best.groupby("commodity", sort=True).head(1)

    def save(fig, index):
        fig.savefig(output / FIGURES[index], dpi=140, metadata={"Software": "AgriSense Day 5"})
        plt.close(fig)

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for ax, (_, row) in zip(axes, representatives.iterrows()):
        group = naive.loc[naive.series_id.eq(row.series_id)]
        dates = pd.to_datetime(group.date)
        ax.scatter(dates, group.actual_modal_price, s=16, label="Actual", color=COLORS[row.commodity])
        ax.scatter(dates, group.predicted_modal_price, s=18, marker="x", label="Naive", color="#555555")
        ax.set(title=label(row), ylabel="INR/quintal", ylim=(0, None))
        ax.legend(ncols=2)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
    fig.suptitle("Naive next-observation forecasts — final 60 observed records per series, 2025")
    save(fig, 0)

    for index, (_, row) in enumerate(representatives.iterrows(), start=1):
        group = selected.loc[selected.series_id.eq(row.series_id)]
        fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout="constrained", gridspec_kw={"height_ratios": [2, 1]})
        dates = pd.to_datetime(group.date)
        axes[0].scatter(dates, group.actual_modal_price, s=22, color=COLORS[row.commodity], label="Actual")
        axes[0].scatter(dates, group.predicted_modal_price, s=22, marker="x", color="#555555", label=row.baseline)
        axes[0].set(ylabel="Modal price (INR/quintal)", ylim=(0, None))
        axes[0].legend()
        axes[1].scatter(dates, group.predicted_modal_price - group.actual_modal_price, s=16, color=COLORS[row.commodity])
        axes[1].axhline(0, color="#555555", linewidth=1)
        axes[1].set(ylabel="Prediction − actual\n(INR/quintal)", xlabel="Observed test dates, 2025; no calendar filling")
        axes[1].xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        fig.suptitle(f"{label(row)}\nValidation-selected: {row.baseline}; test MAE {row.mae:.1f} INR/quintal", fontsize=11)
        save(fig, index)

    values = aggregate.loc[aggregate.phase.eq("test")].sort_values(["median_mae", "baseline"])
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    ax.barh(values.baseline, values.median_mae, color="#375f91")
    ax.invert_yaxis()
    ax.set(title="Test baseline comparison — median across nine separate series", xlabel="Median per-series MAE (INR/quintal)")
    save(fig, 4)

    fig, ax = plt.subplots(figsize=(14, 7), layout="constrained")
    labels = [label(row) + f" [{row['baseline']}]" for row in best.to_dict("records")]
    bars = ax.barh(labels, best.mae, color=[COLORS[name] for name in best.commodity])
    ax.bar_label(bars, fmt="{:.1f}", padding=3)
    ax.invert_yaxis()
    ax.tick_params(axis="y", labelsize=8)
    ax.set(title="Baseline selected on validation — later test performance", xlabel="Test MAE (INR/quintal)", xlim=(0, best.mae.max() * 1.18))
    save(fig, 5)

    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    names = sorted(COLORS)
    ax.boxplot([selected.loc[selected.commodity.eq(name), "absolute_error"] for name in names], tick_labels=names,
               flierprops={"markersize": 3, "alpha": .5})
    ax.set(title="Selected-baseline test errors — pooled errors, not pooled prices", ylabel="Absolute error (INR/quintal)", ylim=(0, None))
    save(fig, 6)

    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    for name in names:
        group = selected.loc[selected.commodity.eq(name)]
        ax.scatter(group.gap_days, group.absolute_error, s=16, alpha=.4, label=name, color=COLORS[name])
    ax.set(title="Selected-baseline test error vs elapsed observation gap", xlabel="Calendar days from previous observation (1 = consecutive days)",
           ylabel="Absolute error (INR/quintal)", ylim=(0, None), xlim=(.5, selected.gap_days.max() + .5))
    ax.legend()
    save(fig, 7)


def build_report(summary, best, aggregate, gaps, examples):
    winners = [{"Series (Gujarat)": label(row), "Selected baseline": row["baseline"],
                "Validation MAE": round(row["validation_mae"], 2), "Test MAE": round(row["mae"], 2),
                "Test RMSE": round(row["rmse"], 2), "Test sMAPE %": round(row["smape"], 2),
                "Test rank": row["rank"]} for row in best.to_dict("records")]
    comparison = aggregate.loc[aggregate.phase.eq("test")].sort_values(["median_mae", "baseline"]).round(3)
    biggest = examples.sort_values(["absolute_error", "series_id", "date"], ascending=[False, True, True]).head(5)
    errors = [{"Series": label(row), "Date": row["date"], "Actual": round(row["actual_modal_price"], 2),
               "Prediction": round(row["predicted_modal_price"], 2), "Abs error": round(row["absolute_error"], 2),
               "Gap days": row["gap_days"], "Observed move %": round(row["observed_price_change_pct"], 1)} for row in biggest.to_dict("records")]
    text = ["# Day 5: forecasting baselines and chronological backtesting",
            "Krishkumar | 2401CS83 | IIT Patna\n\nRepository: https://github.com/Krish290107/agrisense",
            "## Scope and evaluation", f"{summary['candidate_series']} exact Day 4 candidate series; {summary['forecast_comparisons']:,} forecast/actual comparisons from {summary['unique_evaluation_targets']} observed target records across seven baselines. Prices are INR/quintal. Full six-field identities come from forecast_candidates.csv and are checked against readiness, EDA summary and cleaned data.",
            f"Each series uses its final 120 observations: first 60 for validation, final 60 for test. This leaves {summary['initial_history_range']['minimum']}–{summary['initial_history_range']['maximum']} initial observations in the supplied candidates. Forecasts expand the history one observed record at a time. Earlier validation/test actuals become available only after their forecast is scored. Every forecast uses strictly earlier modal prices; no current/future min/max, target, date gap or exogenous variable enters the model.",
            "The horizon is the next observed record, not tomorrow or a fixed calendar interval. Target dates and elapsed gaps are attached retrospectively for scoring, not assumed known at the forecast origin. Each series has its own dates; baseline_splits.csv freezes boundaries and sample counts. No missing observations are created or filled.",
            "Model selection uses validation MAE, then validation RMSE, then baseline name as a deterministic tie-break. The selected model is frozen before test. best_baselines.csv contains that model's later test scores, not a model chosen by looking at test scores. baseline_metrics.csv additionally ranks all models separately within each phase; test rank 1 is a retrospective diagnostic, not an unbiased model-selection result.",
            "## Baselines and metrics", "Naive = previous observed price. Historical mean/median use all preceding observations. Rolling means use the previous 3, 5 or 7 observations; rolling median uses the previous 5. Windows are fixed in advance, count actual records and are small relative to available history. No seasonal baseline: each identity spans under two years, observation intervals are irregular and there are too few repeated seasonal cycles to justify a weekly/monthly/yearly rule.",
            "MAE = mean absolute error; RMSE = square root of mean squared error. Both are INR/quintal; MAE 250 means an average absolute miss of 250 INR/quintal over scored targets. sMAPE = 100 × mean(2|prediction−actual|/(|actual|+|prediction|)), range 0–200%; a zero/zero pair contributes 0. Canonical actuals and forecasts here are positive. Scores use forecast pairs only, never training observations.",
            "## Validation-selected baseline per series", table(winners, ["Series (Gujarat)", "Selected baseline", "Validation MAE", "Test MAE", "Test RMSE", "Test sMAPE %", "Test rank"]),
            "## Aggregate comparison", table(comparison.to_dict("records"), ["baseline", "mean_mae", "median_mae", "median_rmse", "mean_smape", "phase_wins", "validation_selections"]),
            "These are equal-series summaries of test metrics, not a concatenated price series. phase_wins counts retrospective test winners; validation_selections counts models chosen earlier. Ties are broken deterministically, not treated as evidence of meaningful superiority. Selected-baseline test mean MAE: " + f"{summary['selected_test_metrics']['mean_series_mae']:.2f}; median MAE: {summary['selected_test_metrics']['median_series_mae']:.2f} INR/quintal.",
            "## Error and gap analysis", table(errors, ["Series", "Date", "Actual", "Prediction", "Abs error", "Gap days", "Observed move %"]),
            table(summary["commodity_test_errors"], ["commodity", "comparisons", "mae", "rmse", "smape"]),
            "Largest selected-model misses are shown above, with the actual price move from the previous observation. A large observed move is not proof of an erroneous source value. All observations, including genuine spikes, remain. baseline_error_examples.csv includes the top three errors for every series.",
            f"Selected-baseline pooled test MAE is {summary['gap_comparison']['consecutive']['mae']:.2f} over {summary['gap_comparison']['consecutive']['count']} consecutive-day targets versus {summary['gap_comparison']['longer']['mae']:.2f} over {summary['gap_comparison']['longer']['count']} longer-gap targets. This observed association is not causal or adjusted for commodity/market composition. The largest individual miss occurs at an elapsed gap of {int(biggest.iloc[0].gap_days)} day(s), so long gaps alone do not explain spikes. {summary['unchanged_test_price_fraction']:.1%} of test targets repeat their preceding observed price; this favors persistence but does not prove the source reporting process is unchanged.",
            table(gaps.loc[gaps.policy.eq("validation_selected")].round(3).to_dict("records"), ["commodity", "gap_band_days", "comparisons", "mae", "rmse"]),
            "Gap days are elapsed days (1 means consecutive dates), unlike Day 4's count of missing days between dates. Gap buckets are retrospective diagnostics; sample sizes and different series/price levels confound comparisons. Sparse long-gap buckets cannot establish that elapsed time causes error. Compare the companion naive rows in baseline_gap_errors.csv before generalizing.",
            "## Figures", *[f"![{name[3:-4].replace('_', ' ')}](../figures/baselines/{name})" for name in FIGURES],
            "Representative plots use the first exact candidate per commodity in deterministic identity order; selection does not depend on test error. Points are observed dates; no interpolated price line is a generated forecast.",
            "## Reproduction and future benchmark contract", "Run `.\\.venv\\Scripts\\python.exe scripts/run_baselines.py`. Summary records input/code hashes, software versions, fixed policy and output hashes. Prediction-level results are local at reports/data/local/baseline_predictions.csv; compact metrics/splits/reports are shareable. Repeated execution with the same inputs and environment is deterministic. The existing summary prevents silently overwriting scores after an input, policy or implementation change; use a separately reviewed/versioned experiment for a changed benchmark.",
            "Future models must use the same exact identities, target dates, one-observation horizon, history availability and metric definitions. Fit transforms/features only on past training observations, tune on validation, then score the same test dates. Keep Day 5 scores unchanged. Once later development uses these test findings, this test is no longer a fresh unbiased holdout; reserve additional untouched data for a final generalization claim.",
            "## Limitations and Day 6", "Only the strongest nine candidates are evaluated; Day 4 selected them using full-history coverage/variability, so the cohort is retrospective and not representative of all 229 series. No forecast computation uses future targets, but this cohort-selection bias limits generalization. Approximately two source years and less than two years per identity do not establish stable seasonality. The final 60 observations cover different calendar dates per market and emphasize late-2025 conditions. Historical endpoints are stale; no live forecasting capability is claimed. There is no publication-time metadata, so evaluation assumes earlier recorded observations were available without later revision. Weather, arrivals, demand and events are absent. Baseline performance is not production readiness.",
            "Day 6 should build strictly historical per-series features with explicit availability and leakage tests, retaining the fixed Day 5 benchmark for later comparisons."]
    return "\n\n".join(text) + "\n"


def run_baselines():
    frame, candidates, input_hashes = load_inputs()
    code_hashes = {name: file_digest(ROOT / name) for name in ["scripts/run_baselines.py", "scripts/run_eda.py", "scripts/market_data_common.py", "scripts/clean_market_data.py"]}
    software = {"pandas": pd.__version__, "numpy": np.__version__, "matplotlib": matplotlib.__version__}
    benchmark = {"inputs": input_hashes, "code": code_hashes, "policy": POLICY, "baselines": BASELINES, "software": software}
    benchmark_id = digest(json.dumps(benchmark, sort_keys=True).encode())
    output, figures = ROOT / "reports/data", ROOT / "reports/figures/baselines"
    summary_path = output / "baseline_summary.json"
    if summary_path.exists() and json.loads(summary_path.read_text(encoding="utf-8")).get("benchmark_id") != benchmark_id:
        raise ValueError("Existing Day 5 benchmark has different inputs/code/policy/software. Preserve it and create a separately reviewed, versioned experiment; no outputs overwritten.")
    predictions, splits = [], []
    for candidate in candidates.to_dict("records"):
        group = frame.loc[(frame[SERIES_FIELDS] == pd.Series({field: candidate[field] for field in SERIES_FIELDS})).all(axis=1)]
        predicted, split = backtest_series(group, candidate["series_id"], POLICY["validation_observations"], POLICY["test_observations"], POLICY["minimum_initial_history"])
        predictions.append(predicted)
        splits.append(split)
    predictions = pd.concat(predictions, ignore_index=True).sort_values([*SERIES_FIELDS, "date", "baseline"], kind="stable").reset_index(drop=True)
    scores, best, aggregate = score_predictions(predictions)
    selected, naive, gaps, examples = analyze_errors(predictions, best)
    if not np.isfinite(scores[["mae", "rmse", "smape"]].to_numpy()).all():
        raise ValueError("Non-finite benchmark metrics; no outputs written.")
    if not (pd.to_datetime(predictions.previous_observation_date) < pd.to_datetime(predictions.date)).all():
        raise ValueError("Non-chronological forecast origin detected.")
    summary = {"schema_version": 1, "benchmark_id": benchmark_id, "reproducibility": benchmark,
               "candidate_series": len(candidates), "forecast_comparisons": len(predictions),
               "initial_history_range": {"minimum": min(row["initial_train_observations"] for row in splits), "maximum": max(row["initial_train_observations"] for row in splits)},
               "unique_evaluation_targets": len(predictions[["series_id", "date"]].drop_duplicates()),
               "comparisons_by_phase": {str(k): int(v) for k, v in predictions.phase.value_counts().sort_index().items()},
               "evaluation_method": "Expanding-history, one observed step ahead; validation selection then frozen-model walk-forward test",
               "baselines": BASELINES, "policy": POLICY, "aggregate_metrics": json.loads(aggregate.to_json(orient="records")),
               "validation_winners": {str(k): int(v) for k, v in best.baseline.value_counts().sort_index().items()},
               "retrospective_test_winners": {str(k): int(v) for k, v in scores.loc[scores.phase.eq("test") & scores["rank"].eq(1), "baseline"].value_counts().sort_index().items()},
               "best_baselines": json.loads(best.to_json(orient="records")),
               "selected_test_metrics": {"mean_series_mae": float(best.mae.mean()), "median_series_mae": float(best.mae.median()),
                                         "pooled_pairs": metrics(selected.actual_modal_price, selected.predicted_modal_price)},
               "commodity_test_errors": [{"commodity": name, "comparisons": len(group), **metrics(group.actual_modal_price, group.predicted_modal_price)} for name, group in selected.groupby("commodity", sort=True)],
               "gap_comparison": {name: {"count": int(mask.sum()), "mae": float(selected.loc[mask, "absolute_error"].mean()) if mask.any() else None}
                                  for name, mask in [("consecutive", selected.gap_days.eq(1)), ("longer", selected.gap_days.gt(1))]},
               "unchanged_test_price_fraction": float(naive.actual_modal_price.eq(naive.predicted_modal_price).mean()),
               "seasonal_baseline": "Skipped: irregular observations and insufficient repeated annual cycles within exact identities",
               "generated_files": [*TABLES, "local/baseline_predictions.csv", "baseline_summary.json", "BASELINE_FORECAST_REPORT.md"],
               "generated_figures": FIGURES}
    for path, checksum in input_hashes.items():
        if file_digest(ROOT / path) != checksum:
            raise ValueError("Input changed during evaluation; no outputs written.")
    (output / "local").mkdir(parents=True, exist_ok=True)
    tables = [scores, best, aggregate, pd.DataFrame(splits), gaps, examples]
    for filename, content in zip(TABLES + ["local/baseline_predictions.csv"], tables + [predictions]):
        content.to_csv(output / filename, index=False, lineterminator="\n", float_format="%.15g")
    make_figures(predictions, best, aggregate, selected, naive, figures)
    (output / "BASELINE_FORECAST_REPORT.md").write_text(build_report(summary, best, aggregate, gaps, examples), encoding="utf-8", newline="\n")
    artifacts = [output / name for name in [*TABLES, "local/baseline_predictions.csv", "BASELINE_FORECAST_REPORT.md"]] + [figures / name for name in FIGURES]
    summary["artifact_sha256"] = {str(path.relative_to(ROOT)): file_digest(path) for path in artifacts}
    write_json(summary_path, summary)
    print(f"Evaluated {len(candidates)} series; {len(predictions):,} comparisons; {len(BASELINES)} baselines. Selected test mean MAE: {best.mae.mean():.2f} INR/quintal.")
    print("Report: reports/data/BASELINE_FORECAST_REPORT.md; figures: reports/figures/baselines")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        run_baselines()
    except (ValueError, OSError, KeyError) as exc:
        print(f"Baseline evaluation failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
