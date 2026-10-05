"""Validation-selected per-series regressors, preserving the Day 5 test dates."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import ExtraTreesRegressor, GradientBoostingRegressor, HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from threadpoolctl import threadpool_limits

from build_features import protected_inputs
from market_data_common import ROOT, SERIES_FIELDS, digest, file_digest, write_json
from run_baselines import metrics
from run_eda import COLORS, label, table

SEED = 42
CONFIGS = [
    {"id": "ridge_1", "model": "Ridge", "params": {"alpha": 1.0}},
    {"id": "ridge_10", "model": "Ridge", "params": {"alpha": 10.0}},
    {"id": "rf_leaf3", "model": "RandomForest", "params": {"n_estimators": 100, "max_depth": 6, "min_samples_leaf": 3, "max_features": 1.0}},
    {"id": "rf_leaf8", "model": "RandomForest", "params": {"n_estimators": 100, "max_depth": 6, "min_samples_leaf": 8, "max_features": 1.0}},
    {"id": "extra_trees", "model": "ExtraTrees", "params": {"n_estimators": 100, "max_depth": 6, "min_samples_leaf": 3, "max_features": 1.0}},
    {"id": "gradient_boosting", "model": "GradientBoosting", "params": {"n_estimators": 100, "learning_rate": .05, "max_depth": 2, "min_samples_leaf": 8}},
    {"id": "hist_gradient_boosting", "model": "HistGradientBoosting", "params": {"max_iter": 100, "learning_rate": .05, "max_leaf_nodes": 15, "min_samples_leaf": 15, "l2_regularization": 1.0, "early_stopping": False}},
]
POLICY = {"strategy": "Separate model selection per exact series; no cross-series future outcomes",
          "features": "Day 6 historical_only_feature_names; target-date features excluded",
          "selection": "Per-series validation MAE, then RMSE, then fixed configuration order",
          "refit": "Frozen configuration refitted on own train+validation before own test start",
          "test": "One-step observed-record features updated with earlier actuals; model weights fixed throughout test",
          "seed": SEED, "threads": 1, "prediction_clipping": "none"}
FIGURES = ["01_validation_mae.png", "02_baseline_vs_ml.png", "03_onion_predictions.png",
           "04_potato_predictions.png", "05_tomato_predictions.png", "06_residuals.png",
           "07_improvement.png", "08_feature_importance.png", "09_error_vs_gap.png"]


def make_pipeline(config, feature_names):
    if set(feature_names) & {"modal_price", "min_price", "max_price", "split", "date", "series_id", *SERIES_FIELDS}:
        raise ValueError("Predictor list contains target, context or same-row raw prices.")
    model_type, params = config["model"], config["params"]
    classes = {"Ridge": Ridge, "RandomForest": RandomForestRegressor, "ExtraTrees": ExtraTreesRegressor,
               "GradientBoosting": GradientBoostingRegressor, "HistGradientBoosting": HistGradientBoostingRegressor}
    options = dict(params)
    if model_type != "Ridge":
        options["random_state"] = SEED
    if model_type in {"RandomForest", "ExtraTrees"}:
        options["n_jobs"] = 1
    if model_type == "Ridge":
        options["solver"] = "svd"
    transform = ColumnTransformer([
        ("numeric", StandardScaler() if model_type == "Ridge" else "passthrough", feature_names),
        ("identity", OneHotEncoder(handle_unknown="ignore", sparse_output=False), SERIES_FIELDS),
    ], remainder="drop", sparse_threshold=0)
    return Pipeline([("preprocess", transform), ("model", classes[model_type](**options))])


def partition(frame):
    if set(frame.split) != {"train", "validation", "test"}:
        raise ValueError("Expected explicit train/validation/test labels.")
    if frame.duplicated([*SERIES_FIELDS, "date"]).any():
        raise ValueError("Duplicate model target rows.")
    parts = {phase: frame.loc[frame.split.eq(phase)].copy() for phase in ["train", "validation", "test"]}
    if not all(set(part.series_id) == set(frame.series_id) for part in parts.values()):
        raise ValueError("Every series must have every evaluation region.")
    for sid, group in frame.groupby("series_id"):
        if len(group[SERIES_FIELDS].drop_duplicates()) != 1:
            raise ValueError("A series ID maps to more than one identity.")
        train, validation, test = [parts[name].loc[parts[name].series_id.eq(sid)] for name in parts]
        if not train.date.max() < validation.date.min() <= validation.date.max() < test.date.min():
            raise ValueError("Within-series chronological regions overlap.")
    return parts


def select_models(train, validation, features, configs=None):
    if not train.split.eq("train").all() or not validation.split.eq("validation").all():
        raise ValueError("Selection accepts TRAIN and VALIDATION only, never TEST.")
    if set(train.series_id) != set(validation.series_id):
        raise ValueError("Training and validation series do not match.")
    configurations = configs if configs is not None else CONFIGS
    records = []
    for sid, initial in train.groupby("series_id", sort=True):
        valid = validation.loc[validation.series_id.eq(sid)]
        if initial.date.max() >= valid.date.min():
            raise ValueError("Training precedes validation for each exact series.")
        identity = initial.iloc[0][SERIES_FIELDS].to_dict()
        for order, config in enumerate(configurations):
            pipeline = make_pipeline(config, features)
            pipeline.fit(initial[SERIES_FIELDS + features], initial.modal_price)
            predicted = pipeline.predict(valid[SERIES_FIELDS + features])
            train_predicted = pipeline.predict(initial[SERIES_FIELDS + features])
            records.append({**identity, "series_id": sid, "config_id": config["id"], "model": config["model"],
                            "hyperparameters": json.dumps(config["params"], sort_keys=True), "complexity_order": order,
                            "train_rows": len(initial), "validation_rows": len(valid),
                            "train_mae": metrics(initial.modal_price, train_predicted)["mae"],
                            **{f"validation_{name}": value for name, value in metrics(valid.modal_price, predicted).items()}})
    scores = pd.DataFrame(records).sort_values(["series_id", "validation_mae", "validation_rmse", "complexity_order"], kind="stable")
    scores["rank"] = scores.groupby("series_id").cumcount() + 1
    selected = scores.loc[scores["rank"].eq(1)].sort_values(SERIES_FIELDS).reset_index(drop=True)
    return scores.reset_index(drop=True), selected


def fit_frozen(train, validation, selected, features, configs=None):
    if not train.split.eq("train").all() or not validation.split.eq("validation").all():
        raise ValueError("Final refit excludes test observations.")
    configurations = {config["id"]: config for config in (configs if configs is not None else CONFIGS)}
    allowed = pd.concat([train, validation]).sort_values([*SERIES_FIELDS, "date"])
    bundle = {"schema_version": 1, "feature_names": list(features), "identity_columns": SERIES_FIELDS,
              "target": "modal_price", "unit": "INR/quintal", "models": {}, "identities": {}, "fit_last_dates": {}}
    for row in selected.to_dict("records"):
        group = allowed.loc[allowed.series_id.eq(row["series_id"])]
        pipeline = make_pipeline(configurations[row["config_id"]], features)
        pipeline.fit(group[SERIES_FIELDS + features], group.modal_price)
        bundle["models"][row["series_id"]] = pipeline
        bundle["identities"][row["series_id"]] = {field: row[field] for field in SERIES_FIELDS}
        bundle["fit_last_dates"][row["series_id"]] = group.date.max().date().isoformat()
    return bundle


def predict_bundle(bundle, frame):
    results = pd.Series(index=frame.index, dtype=float)
    for sid, group in frame.groupby("series_id", sort=True):
        if sid not in bundle["models"] or not (group[SERIES_FIELDS] == pd.Series(bundle["identities"][sid])).all().all():
            raise ValueError("Prediction identity does not match the saved exact-series model.")
        results.loc[group.index] = bundle["models"][sid].predict(group[SERIES_FIELDS + bundle["feature_names"]])
    if not np.isfinite(results).all():
        raise ValueError("ML produced non-finite predictions.")
    return results


def compare_baselines(predictions, baseline_predictions, baseline_best, selected):
    baseline = baseline_predictions.loc[baseline_predictions.phase.eq("test")].merge(
        baseline_best[["series_id", "baseline"]], on=["series_id", "baseline"], how="inner", validate="many_to_one")
    keys = [*SERIES_FIELDS, "series_id", "date"]
    baseline = baseline[keys + ["actual_modal_price", "predicted_modal_price", "absolute_error", "baseline", "gap_days"]].rename(
        columns={"actual_modal_price": "baseline_actual", "predicted_modal_price": "baseline_prediction", "absolute_error": "baseline_absolute_error", "baseline": "baseline_name"})
    joined = predictions.merge(baseline, on=keys, how="outer", validate="one_to_one", indicator=True)
    if not joined["_merge"].eq("both").all() or not np.array_equal(joined.actual_modal_price, joined.baseline_actual):
        raise ValueError("ML and baseline identities/dates/actual targets must match exactly.")
    joined = joined.drop(columns=["_merge", "baseline_actual"])
    comparisons = []
    for sid, group in joined.groupby("series_id", sort=True):
        identity = group.iloc[0][SERIES_FIELDS].to_dict()
        ml = metrics(group.actual_modal_price, group.predicted_modal_price)
        baseline_mae = float(group.baseline_absolute_error.mean())
        stored = baseline_best.loc[baseline_best.series_id.eq(sid)].iloc[0]
        if not np.isclose(baseline_mae, stored.mae, rtol=1e-12, atol=1e-10):
            raise ValueError("Joined baseline score differs from immutable Day 5 metric.")
        improvement = baseline_mae - ml["mae"]
        choice = selected.loc[selected.series_id.eq(sid)].iloc[0]
        comparisons.append({**identity, "series_id": sid, "test_observations": len(group), "model": choice.model,
                            "config_id": choice.config_id, "baseline_name": group.baseline_name.iloc[0], "baseline_mae": baseline_mae,
                            **{f"ml_{name}": value for name, value in ml.items()}, "absolute_improvement": improvement,
                            "percentage_improvement": 100 * improvement / baseline_mae if baseline_mae else None,
                            "winner": "tie" if abs(improvement) <= 1e-9 else ("ML" if improvement > 0 else "baseline")})
    return joined.sort_values([*SERIES_FIELDS, "date"]).reset_index(drop=True), pd.DataFrame(comparisons).sort_values(SERIES_FIELDS).reset_index(drop=True)


def feature_importance(bundle, train, validation, selected):
    records = []
    for row in selected.to_dict("records"):
        sid = row["series_id"]
        pipeline = bundle["models"][sid]
        model = pipeline.named_steps["model"]
        names = list(pipeline.named_steps["preprocess"].get_feature_names_out())
        if hasattr(model, "feature_importances_"):
            values, method = model.feature_importances_, "training impurity decrease"
        elif hasattr(model, "coef_"):
            values, method = np.abs(model.coef_), "absolute standardized-numeric coefficients"
        else:
            # Explain a training-only fit on validation, never the test targets.
            from sklearn.inspection import permutation_importance
            initial = train.loc[train.series_id.eq(sid)]
            valid = validation.loc[validation.series_id.eq(sid)]
            config = next(item for item in CONFIGS if item["id"] == row["config_id"])
            explanatory = make_pipeline(config, bundle["feature_names"])
            explanatory.fit(initial[SERIES_FIELDS + bundle["feature_names"]], initial.modal_price)
            importance = permutation_importance(explanatory, valid[SERIES_FIELDS + bundle["feature_names"]], valid.modal_price,
                                               scoring="neg_mean_absolute_error", n_repeats=3, random_state=SEED, n_jobs=1)
            names, values, method = SERIES_FIELDS + bundle["feature_names"], np.maximum(importance.importances_mean, 0), "validation permutation MAE on training-only fit; negative importance truncated for share"
        total = float(np.sum(values))
        for name, value in zip(names, values):
            feature = name.removeprefix("numeric__")
            if name.startswith("identity__"):
                feature = next(field for field in SERIES_FIELDS if name.removeprefix("identity__").startswith(field + "_"))
            records.append({"series_id": sid, "feature": feature, "importance": float(value),
                            "normalized_share": float(value / total) if total else 0, "method": method})
    detail = pd.DataFrame(records)
    aggregated = detail.groupby("feature", sort=True).normalized_share.sum().div(len(bundle["models"])).sort_values(ascending=False).reset_index()
    return detail, aggregated


def load_feature_inputs():
    benchmark, protected = protected_inputs()
    feature_summary_path = ROOT / "reports/data/feature_summary.json"
    feature_summary = json.loads(feature_summary_path.read_text(encoding="utf-8"))
    for relative, checksum in feature_summary["output_sha256"].items():
        if file_digest(ROOT / relative) != checksum:
            raise ValueError("Day 6 feature artifact differs from its recorded hash.")
    if feature_summary["baseline_benchmark_id"] != benchmark["benchmark_id"]:
        raise ValueError("Day 6 features refer to another Day 5 benchmark.")
    protected.update(feature_summary["output_sha256"])
    protected[str(feature_summary_path.relative_to(ROOT))] = file_digest(feature_summary_path)
    metadata = json.loads((ROOT / "reports/data/feature_metadata.json").read_text(encoding="utf-8"))
    all_features, features = metadata["feature_names"], metadata["historical_only_feature_names"]
    conditional = metadata["requires_known_target_date"]
    if set(features) & set(conditional) or set(features) | set(conditional) != set(all_features):
        raise ValueError("Feature availability lists disagree.")
    for item in metadata["features"]:
        if item["name"] in features and item["uses_target_date"]:
            raise ValueError("Historical-only feature uses target date.")
    frame = pd.read_csv(ROOT / "data/processed/forecast_features.csv", parse_dates=["date"], keep_default_na=False)
    if not np.isfinite(frame[all_features].to_numpy(dtype=float)).all():
        raise ValueError("ML features are incomplete; no imputation is authorized/needed.")
    parts = partition(frame)
    if {phase: len(rows) for phase, rows in parts.items()} != feature_summary["rows_by_split"] or len(frame.series_id.unique()) != feature_summary["candidate_series"]:
        raise ValueError("Feature counts disagree with Day 6 summary.")
    return frame, parts, features, metadata, protected


def plot_results(scores, predictions, comparison, importance, directory):
    directory.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.alpha": .18, "figure.facecolor": "white"})
    def save(fig, i):
        fig.savefig(directory / FIGURES[i], dpi=140, facecolor="white", metadata={"Software": "AgriSense Day 7"})
        plt.close(fig)
    macro = scores.groupby("config_id").validation_mae.mean().sort_values()
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    ax.barh(macro.index, macro.values, color="#375f91"); ax.invert_yaxis()
    ax.set(title="Validation comparison — macro MAE across per-series fits", xlabel="Validation MAE (INR/quintal)")
    save(fig, 0)
    labels = [label(row) for row in comparison.to_dict("records")]
    y = np.arange(len(comparison))
    fig, ax = plt.subplots(figsize=(14, 7), layout="constrained")
    ax.barh(y - .18, comparison.baseline_mae, height=.35, label="Day 5 selected baseline", color="#999999")
    ax.barh(y + .18, comparison.ml_mae, height=.35, label="Validation-selected ML", color="#375f91")
    ax.set_yticks(y, labels, fontsize=8); ax.invert_yaxis(); ax.legend()
    ax.set(title="Exact-series test MAE — unchanged Day 5 target dates", xlabel="MAE (INR/quintal)")
    save(fig, 1)
    for i, commodity in enumerate(sorted(COLORS), start=2):
        row = comparison.loc[comparison.commodity.eq(commodity)].iloc[0]
        group = predictions.loc[predictions.series_id.eq(row.series_id)]
        fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
        ax.scatter(group.date, group.actual_modal_price, s=18, label="Actual", color=COLORS[commodity])
        ax.scatter(group.date, group.predicted_modal_price, s=20, marker="x", label="ML", color="#375f91")
        ax.scatter(group.date, group.baseline_prediction, s=12, marker="+", label="Baseline", color="#777777")
        ax.set(title=f"{label(row)}\n{row.config_id} — observed test points only", ylabel="Modal price (INR/quintal)", xlabel="2025 test dates", ylim=(min(0, group.predicted_modal_price.min()), None))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b")); ax.legend()
        save(fig, i)
    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    names = sorted(COLORS)
    ax.boxplot([predictions.loc[predictions.commodity.eq(name), "signed_error"] for name in names], tick_labels=names)
    ax.axhline(0, color="#777777", linewidth=1)
    ax.set(title="Test residuals by commodity — observed errors pooled", ylabel="Prediction − actual (INR/quintal)")
    save(fig, 5)
    fig, ax = plt.subplots(figsize=(14, 7), layout="constrained")
    ax.barh(labels, comparison.absolute_improvement, color=["#43856a" if n > 0 else "#c44c45" for n in comparison.absolute_improvement])
    ax.invert_yaxis(); ax.axvline(0, color="#777777"); ax.tick_params(axis="y", labelsize=8)
    ax.set(title="Test improvement — positive means ML has lower MAE", xlabel="Baseline MAE − ML MAE (INR/quintal)")
    save(fig, 6)
    fig, ax = plt.subplots(figsize=(11, 6), layout="constrained")
    top = importance.head(10)
    ax.barh(top.feature, top.normalized_share, color="#375f91"); ax.invert_yaxis()
    ax.set(title="Model-specific importance — normalized within model, averaged across series", xlabel="Mean normalized share (descriptive; methods differ)")
    save(fig, 7)
    fig, ax = plt.subplots(figsize=(10, 5), layout="constrained")
    for name in names:
        group = predictions.loc[predictions.commodity.eq(name)]
        ax.scatter(group.gap_days, group.absolute_error, s=18, alpha=.5, label=name, color=COLORS[name])
    ax.set(title="ML test error vs elapsed gap — diagnostic only", xlabel="Days from previous observation", ylabel="Absolute error (INR/quintal)", ylim=(0, None)); ax.legend()
    save(fig, 8)


def report(summary, selected, comparison, scores, diagnostic):
    selection = [{"Series": label(r), "Config": r["config_id"], "Train MAE": round(r["train_mae"], 2),
                  "Validation MAE": round(r["validation_mae"], 2), "Validation RMSE": round(r["validation_rmse"], 2)} for r in selected.to_dict("records")]
    rows = [{"Series": label(r), "Baseline": r["baseline_name"], "Baseline MAE": round(r["baseline_mae"], 2),
             "ML MAE": round(r["ml_mae"], 2), "Improvement %": round(r["percentage_improvement"], 2), "Winner": r["winner"]} for r in comparison.to_dict("records")]
    a = summary["test_aggregate"]
    text = ["# Day 7: ML training, validation and baseline comparison", "Krishkumar | 2401CS83 | IIT Patna\n\nRepository: https://github.com/Krish290107/agrisense",
            "## Design and availability", "All 27 Day 6 features were checked. Only the 21 historical-only numeric features are used, plus six identity columns encoded inside each pipeline. The six target-date features depend only on dates, not target-day prices, but the next reporting date is not proven knowable operationally. Excluding them preserves Day 5's unknown-next-date information contract. No target, date, split, raw current min/max, benchmark errors or benchmark predictions enter the model.",
            "Separate models are selected per exact series. A single pooled model using all nominal TRAIN rows would see outcomes later than the earliest validation origins; using all validation rows for global selection would also see outcomes after some test origins. Inspection found cross-series temporal overlap. Per-series selection preserves all 4,011 train, 540 validation and 540 test rows without moving boundaries or sharing future outcomes across markets. A synchronized global experiment is deferred; no superiority over global modeling is claimed.",
            "Seven fixed configurations from five families: Ridge alpha 1/10; Random Forest 100 trees, depth 6, leaves 3/8; Extra Trees 100 trees, depth 6, leaf 3; Gradient Boosting 100 trees, rate .05, depth 2, leaf 8; HistGradientBoosting 100 iterations, rate .05, 15 leaves, minimum leaf 15, L2=1, early stopping disabled. Seed 42; one thread. No random cross-validation, target transform, clipping or imputation. Ridge scales numeric inputs; trees do not. OneHotEncoder(handle_unknown='ignore') fits on allowed data only; identity categories are constant within each local model, not arbitrary numeric IDs.",
            "## Validation-only selection", table(selection, ["Series", "Config", "Train MAE", "Validation MAE", "Validation RMSE"]),
            f"Selected configurations have macro validation MAE {summary['validation']['macro_mae']:.2f} and mean per-series RMSE {summary['validation']['macro_rmse']:.2f} INR/quintal. Full validation scores and training errors are in ml_validation_scores.csv. Selection uses per-series validation MAE, then RMSE, then fixed configuration order. Training errors are optimistic in-sample diagnostics, not forecasts. Large train/validation gaps should be revisited in Day 8, not used to retune after test inspection.",
            "Selection was recomputed deterministically using TRAIN and VALIDATION only and frozen in ml_selection.json before test evaluation. Each chosen pipeline was refitted on its own train+validation rows (4,551 total); all fit dates precede that series' first test target. Weights are then fixed during the 60-record test, while historical feature values update with previously observed actual prices. This is one observed step ahead, not recursive multi-day forecasting. Day 5 baselines update their historical formulas each step; this refit-frequency difference is explicit.",
            "## Does ML beat the baselines?", f"ML macro test MAE **{a['macro_mae']:.2f}** versus Day 5 **{a['baseline_macro_mae']:.2f}** INR/quintal: absolute improvement **{a['absolute_improvement']:.2f}**, percentage improvement **{a['percentage_improvement']:.2f}%**. ML wins {a['ml_wins']}/9, baseline wins {a['baseline_wins']}/9, ties {a['ties']}/9. Negative improvement means ML is worse. All selected ML models are evaluated, even when the baseline remains better; no post-test switching is performed.",
            f"Macro median MAE {a['median_mae']:.2f}, mean per-series RMSE {a['macro_rmse']:.2f}. Pooled MAE/RMSE/sMAPE: {a['pooled']['mae']:.2f} / {a['pooled']['rmse']:.2f} / {a['pooled']['smape']:.2f}%. Macro metrics weight series equally; pooled metrics weight observations equally (60 per series here). MAE/RMSE are INR/quintal; sMAPE uses the same 0–200% definition as Day 5.",
            table(rows, ["Series", "Baseline", "Baseline MAE", "ML MAE", "Improvement %", "Winner"]),
            "## Commodity and residual diagnostics", table(pd.DataFrame(summary["commodity_results"]).round(3).to_dict("records"), ["commodity", "ml_mae", "baseline_mae", "improvement", "mean_signed_error"]),
            "Tomato-specific comparisons above retain genuine sharp moves. Positive signed error means overprediction; negative means underprediction. ml_error_examples.csv includes the largest three errors per series, and ml_error_diagnostics.csv reports commodity-specific gap and historical-volatility buckets. The volatility cutoff is each series' TRAIN median rolling_std_7, never a test-chosen threshold. Sample counts and mix confound bucket comparisons; diagnostics do not establish causation and were not used for tuning.",
            "## Explanatory importance", table(pd.DataFrame(summary["top_features"]).round(4).to_dict("records"), ["feature", "normalized_share"]),
            "Importance uses fitted tree impurity or absolute Ridge coefficients (numeric inputs standardized), normalized per model and averaged across nine series. HistGradientBoosting lacks native importance; if selected, deterministic validation permutation importance uses a separate training-only fit of the already frozen configuration. Negative permutation values are truncated only for normalized explanatory shares. Methods and correlated features limit comparisons; none is causal or used for feature selection. No test targets are used for importance.",
            "## Artifacts and reproduction", "Run `.\\.venv\\Scripts\\python.exe scripts/train_models.py`. Existing completed results are verified and reused without selecting/refitting/rescoring test again. The local ml/models/agrisense_price_model.joblib bundle contains every exact-series preprocessing+regression pipeline and routing identity. Model metadata records configuration, schema, counts, hashes, versions, seed and scores. Predictions stay in reports/data/local/ml_test_predictions.csv. Model reload reproduces all final predictions within numeric tolerance. Changed inputs/code/configuration refuse silent overwrite; a future experiment must be separately reviewed/versioned.",
            "## Figures", *[f"![{name[3:-4].replace('_', ' ')}](../figures/models/{name})" for name in FIGURES],
            "## Limits and Day 8", "Although Day 7 does not use test outcomes for fitting or selection, these dates were already analyzed in Days 4/5; they are not a pristine project-wide untouched holdout. The cohort was selected retrospectively, and model-development decisions in this project have seen earlier benchmark reports. Claims of unbiased future generalization require fresh data. Only nine strong candidates, fewer than two years per identity, stale endpoints and unknown release/revision timing further limit applicability. Prior prices are assumed available by the next observation; no weather, arrivals, demand or event data are used. Features lose seven warm-up training rows per series, while baselines retain that context. No production readiness, live forecast API or deployment is claimed. Day 8 should examine robustness and validation-supported choices without silently optimizing this reused test set."]
    return "\n\n".join(text) + "\n"


def run_training():
    frame, parts, features, feature_metadata, protected = load_feature_inputs()
    out, model_dir, figures = ROOT / "reports/data", ROOT / "ml/models", ROOT / "reports/figures/models"
    manifest_path = out / "ml_summary.json"
    software = {"sklearn": sklearn.__version__, "numpy": np.__version__, "pandas": pd.__version__, "joblib": joblib.__version__}
    design = {"input_hashes": protected, "code_sha256": file_digest(Path(__file__)), "configs": CONFIGS,
              "policy": POLICY, "software": software, "features": features}
    experiment_id = digest(json.dumps(design, sort_keys=True).encode())
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing["experiment_id"] != experiment_id:
            raise ValueError("Completed Day 7 experiment differs; preserve its results and use a separately reviewed/versioned experiment.")
        for path, checksum in existing["output_sha256"].items():
            if file_digest(ROOT / path) != checksum:
                raise ValueError(f"Day 7 artifact changed: {path}")
        print("Verified existing Day 7 artifacts; test is not reselected/refitted/rescored.")
        return existing
    train, validation = parts["train"], parts["validation"]
    scores, selected = select_models(train, validation, features)
    repeated_scores, repeated_selected = select_models(train, validation, features)
    pd.testing.assert_frame_equal(scores, repeated_scores, check_exact=False, rtol=1e-10, atol=1e-10)
    pd.testing.assert_frame_equal(selected, repeated_selected, check_exact=False, rtol=1e-10, atol=1e-10)
    selection = {"experiment_id": experiment_id, "design": design, "selection": json.loads(selected.to_json(orient="records")),
                 "validation_determinism_verified": True}
    selection_path = out / "ml_selection.json"
    if selection_path.exists() and json.loads(selection_path.read_text(encoding="utf-8")) != selection:
        raise ValueError("Frozen selection differs; do not replace a reviewed experiment silently.")
    write_json(selection_path, selection)
    bundle = fit_frozen(train, validation, selected, features)
    model_dir.mkdir(parents=True, exist_ok=True)
    model_path = model_dir / "agrisense_price_model.joblib"
    joblib.dump(bundle, model_path, compress=3)
    loaded = joblib.load(model_path)
    test = parts["test"]
    for sid, group in test.groupby("series_id"):
        if pd.Timestamp(bundle["fit_last_dates"][sid]) >= group.date.min():
            raise ValueError("Final fit includes a test-origin or later target.")
    predicted = predict_bundle(bundle, test)
    np.testing.assert_allclose(predicted, predict_bundle(loaded, test), rtol=1e-12, atol=1e-10)
    predictions = test[[*SERIES_FIELDS, "series_id", "date", "modal_price", "rolling_std_7"]].rename(columns={"modal_price": "actual_modal_price"}).copy()
    predictions["predicted_modal_price"] = predicted
    predictions["signed_error"] = predicted - predictions.actual_modal_price
    predictions["absolute_error"] = predictions.signed_error.abs()
    baseline_predictions = pd.read_csv(out / "local/baseline_predictions.csv", parse_dates=["date"])
    baseline_best = pd.read_csv(out / "best_baselines.csv")
    predictions, comparison = compare_baselines(predictions, baseline_predictions, baseline_best, selected)
    detail, importance = feature_importance(bundle, train, validation, selected)
    diagnostic_rows = []
    cutoff = train.groupby("series_id").rolling_std_7.median()
    predictions["historical_volatility_band"] = np.where(predictions.rolling_std_7 > predictions.series_id.map(cutoff), "above_train_median", "at_or_below_train_median")
    predictions["gap_band"] = pd.cut(predictions.gap_days, [0, 1, 3, 7, np.inf], labels=["1", "2–3", "4–7", "8+"]).astype(str)
    for dimension in ["gap_band", "historical_volatility_band"]:
        for (commodity, value), group in predictions.groupby(["commodity", dimension], sort=True):
            diagnostic_rows.append({"dimension": dimension, "commodity": commodity, "bucket": value, "observations": len(group),
                                    "mae": float(group.absolute_error.mean()), "mean_signed_error": float(group.signed_error.mean())})
    diagnostics = pd.DataFrame(diagnostic_rows)
    examples = predictions.sort_values(["series_id", "absolute_error", "date"], ascending=[True, False, True]).groupby("series_id").head(3)
    baseline_macro = float(comparison.baseline_mae.mean()); macro = float(comparison.ml_mae.mean())
    aggregate = {"macro_mae": macro, "median_mae": float(comparison.ml_mae.median()), "macro_rmse": float(comparison.ml_rmse.mean()),
                 "pooled": metrics(predictions.actual_modal_price, predictions.predicted_modal_price), "baseline_macro_mae": baseline_macro,
                 "absolute_improvement": baseline_macro - macro, "percentage_improvement": 100 * (baseline_macro - macro) / baseline_macro,
                 "mean_series_percentage_improvement": float(comparison.percentage_improvement.mean()),
                 "median_series_percentage_improvement": float(comparison.percentage_improvement.median()),
                 "ml_wins": int(comparison.winner.eq("ML").sum()), "baseline_wins": int(comparison.winner.eq("baseline").sum()), "ties": int(comparison.winner.eq("tie").sum())}
    summary = {"schema_version": 1, "experiment_id": experiment_id, "design": design, "strategy": POLICY["strategy"],
               "selected_configurations": json.loads(selected.to_json(orient="records")), "models_evaluated": 5, "configurations_per_series": len(CONFIGS),
               "candidate_series": len(selected), "rows": {phase: len(rows) for phase, rows in parts.items()}, "refit_rows": len(train) + len(validation),
               "target": "modal_price", "unit": "INR/quintal", "feature_schema_version": feature_metadata["schema_version"],
               "numeric_features_used": features, "conditional_features_excluded": feature_metadata["requires_known_target_date"],
               "validation": {"macro_mae": float(selected.validation_mae.mean()), "macro_rmse": float(selected.validation_rmse.mean())},
               "test_aggregate": aggregate, "per_series": json.loads(comparison.to_json(orient="records")),
               "commodity_results": [{"commodity": name, "ml_mae": float(group.absolute_error.mean()), "baseline_mae": float(group.baseline_absolute_error.mean()),
                                      "improvement": float(group.baseline_absolute_error.mean() - group.absolute_error.mean()),
                                      "mean_signed_error": float(group.signed_error.mean())} for name, group in predictions.groupby("commodity", sort=True)],
               "top_features": json.loads(importance.head(5).to_json(orient="records")), "model_artifact": str(model_path.relative_to(ROOT)),
               "reload_verified": True, "validation_determinism_verified": True, "finite_predictions": True,
               "nonpositive_predictions": int(predictions.predicted_modal_price.le(0).sum()), "figures": FIGURES}
    for relative, checksum in protected.items():
        if file_digest(ROOT / relative) != checksum:
            raise ValueError("Protected source changed during training.")
    tables = {"ml_validation_scores.csv": scores, "ml_baseline_comparison.csv": comparison, "ml_feature_importance.csv": detail,
              "ml_error_diagnostics.csv": diagnostics, "ml_error_examples.csv": examples, "local/ml_test_predictions.csv": predictions}
    for name, rows in tables.items():
        rows.to_csv(out / name, index=False, date_format="%Y-%m-%d", lineterminator="\n", float_format="%.15g")
    plot_results(scores, predictions, comparison, importance, figures)
    (out / "ML_MODEL_REPORT.md").write_text(report(summary, selected, comparison, scores, diagnostics), encoding="utf-8", newline="\n")
    write_json(out / "model_metadata.json", summary)
    artifacts = [model_path, selection_path, out / "model_metadata.json", out / "ML_MODEL_REPORT.md", *[out / name for name in tables], *[figures / name for name in FIGURES]]
    summary["output_sha256"] = {str(path.relative_to(ROOT)): file_digest(path) for path in artifacts}
    write_json(manifest_path, summary)
    print(f"Selected {len(selected)} exact-series pipelines; validation macro MAE {summary['validation']['macro_mae']:.2f}.")
    print(f"TEST: ML macro MAE {macro:.2f}, baseline {baseline_macro:.2f}; ML wins {aggregate['ml_wins']}/9. Reload verified.")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        with threadpool_limits(limits=1):
            run_training()
    except (ValueError, OSError, KeyError, AssertionError) as exc:
        print(f"Model training failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
