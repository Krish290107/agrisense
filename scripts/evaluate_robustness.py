"""Day 8 diagnostics on frozen historical choices; never a new holdout."""

from __future__ import annotations

import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from threadpoolctl import threadpool_limits

from market_data_common import ROOT, SERIES_FIELDS, file_digest, write_json
from run_baselines import BASELINES, forecast
from run_eda import label, table
from train_models import CONFIGS, load_feature_inputs, make_pipeline

OUT = ROOT / "reports/data"
VERSION = "day8-v1"
KEYS = [*SERIES_FIELDS, "series_id", "date"]


def error_metrics(actual, predicted):
    a, p = np.asarray(actual, dtype=float), np.asarray(predicted, dtype=float)
    if a.ndim != 1 or a.shape != p.shape or not len(a) or not np.isfinite([a, p]).all():
        raise ValueError("Expected nonempty finite paired vectors")
    e = p - a
    denominator = np.abs(a) + np.abs(p)
    relative = np.divide(np.abs(e), denominator, out=np.zeros_like(e), where=denominator > 0)
    return {"mae": float(np.abs(e).mean()), "rmse": float(np.sqrt(np.square(e).mean())),
            "smape": float(200 * relative.mean()), "bias": float(e.mean()),
            "median_signed_error": float(np.median(e)), "over_rate": float((e > 1e-9).mean()),
            "under_rate": float((e < -1e-9).mean())}


def verify_hashes(hashes):
    for path, expected in hashes.items():
        if file_digest(ROOT / path) != expected:
            raise ValueError(f"Protected artifact changed: {path}")


def reconstruct():
    candidates = pd.read_csv(OUT / "forecast_candidates.csv")
    baseline = pd.read_csv(OUT / "local/baseline_predictions.csv", parse_dates=["date"])
    scores = pd.read_csv(OUT / "baseline_metrics.csv")
    best = pd.read_csv(OUT / "best_baselines.csv")
    ml = pd.read_csv(OUT / "local/ml_test_predictions.csv", parse_dates=["date"])
    comparison = pd.read_csv(OUT / "ml_baseline_comparison.csv")
    identities = candidates[[*SERIES_FIELDS, "series_id"]].sort_values("series_id").reset_index(drop=True)
    if len(identities) != 9 or candidates.series_id.duplicated().any():
        raise ValueError("Expected nine unique candidates")
    for frame in [baseline, best, ml, comparison]:
        actual = frame[[*SERIES_FIELDS, "series_id"]].drop_duplicates().sort_values("series_id").reset_index(drop=True)
        pd.testing.assert_frame_equal(identities, actual)
    if len(baseline) != 7560 or len(ml) != 540 or ml.duplicated(KEYS).any():
        raise ValueError("Historical prediction counts/keys differ")
    rebuilt = []
    for (sid, phase, method), group in baseline.groupby(["series_id", "phase", "baseline"]):
        if len(group) != 60 or group.duplicated(KEYS).any():
            raise ValueError("Historical baseline target count differs")
        result = error_metrics(group.actual_modal_price, group.predicted_modal_price)
        stored = scores.loc[scores.series_id.eq(sid) & scores.phase.eq(phase) & scores.baseline.eq(method)]
        if len(stored) != 1:
            raise ValueError("Missing/duplicate baseline metric")
        np.testing.assert_allclose([result[x] for x in ["mae", "rmse", "smape"]], stored.iloc[0][["mae", "rmse", "smape"]].astype(float), rtol=1e-10, atol=1e-9)
        rebuilt.append({"series_id": sid, "phase": phase, "baseline": method, **result})
    rebuilt = pd.DataFrame(rebuilt).sort_values(["series_id", "phase", "mae", "rmse", "baseline"])
    rebuilt["rank"] = rebuilt.groupby(["series_id", "phase"]).cumcount() + 1
    ranks = rebuilt.merge(scores, on=["series_id", "phase", "baseline"], suffixes=("_new", "_old"), validate="one_to_one")
    rank_notes = []
    for (sid, phase), tied in ranks.loc[~ranks.rank_new.eq(ranks.rank_old)].groupby(["series_id", "phase"]):
        if not np.allclose(tied.mae_new, tied.mae_new.iloc[0], rtol=0, atol=1e-9):
            raise ValueError("Historical ranking differs beyond numerical tolerance")
        rank_notes.append({"series_id": sid, "phase": phase, "methods": tied.baseline.tolist(),
                           "reason": "Sub-nanorupee MAE ties change nonwinning rank order after CSV roundtrip; preserve original ranks."})
    winners = rebuilt.loc[rebuilt.phase.eq("validation") & rebuilt["rank"].eq(1)]
    chosen = winners.merge(best, on=["series_id", "baseline"], validate="one_to_one")
    if len(chosen) != 9:
        raise ValueError("Validation-selected baselines differ")
    selected = baseline.loc[baseline.phase.eq("test")].merge(best[["series_id", "baseline"]], on=["series_id", "baseline"], validate="many_to_one")
    aligned = ml.merge(selected[KEYS + ["actual_modal_price", "predicted_modal_price"]], on=KEYS, suffixes=("", "_baseline"), how="outer", validate="one_to_one", indicator=True)
    if not aligned._merge.eq("both").all():
        raise ValueError("Historical targets differ")
    np.testing.assert_array_equal(aligned.actual_modal_price, aligned.actual_modal_price_baseline)
    np.testing.assert_allclose(aligned.baseline_prediction, aligned.predicted_modal_price_baseline, atol=1e-9)
    for sid, group in ml.groupby("series_id"):
        result = error_metrics(group.actual_modal_price, group.predicted_modal_price)
        row = comparison.loc[comparison.series_id.eq(sid)].iloc[0]
        np.testing.assert_allclose([result[x] for x in ["mae", "rmse", "smape"]], [row.ml_mae, row.ml_rmse, row.ml_smape], rtol=1e-10, atol=1e-9)
        if len(group) != 60:
            raise ValueError("ML count differs")
        base = error_metrics(group.actual_modal_price, group.baseline_prediction)["mae"]
        np.testing.assert_allclose(base, row.baseline_mae, atol=1e-9)
        if ("ML" if result["mae"] < base else "baseline") .lower() != str(row.winner).lower():
            raise ValueError("Historical comparison winner differs")
    result = {"baseline_metric_rows_verified": len(rebuilt), "baseline_predictions": len(baseline),
              "ml_predictions": len(ml), "candidate_series": 9, "metric_discrepancies_beyond_tolerance": 0,
              "rank_roundtrip_notes": rank_notes,
              "baseline": error_metrics(selected.actual_modal_price, selected.predicted_modal_price),
              "ml": error_metrics(ml.actual_modal_price, ml.predicted_modal_price),
              "gap_distribution": {str(k): int(v) for k, v in selected.gap_days.value_counts().sort_index().items()}}
    return result, candidates, baseline, best, ml


def windows(group, block_size=20):
    group = group.sort_values("date")
    if group.date.duplicated().any() or len(group[SERIES_FIELDS].drop_duplicates()) != 1:
        raise ValueError("Windows require unique dates and exactly one identity")
    targets = group.loc[group.split.eq("test")]
    if len(targets) != 3 * block_size:
        raise ValueError("Expected three complete chronological blocks")
    for index in range(3):
        block = targets.iloc[index * block_size:(index + 1) * block_size]
        past = group.loc[group.date.lt(block.date.min())]
        if past.empty or past.date.max() >= block.date.min():
            raise ValueError("Origin contains future targets")
        yield index + 1, past, block


def gap_band(days):
    if not np.isfinite(days) or days < 1 or int(days) != days:
        raise ValueError("Gap must be a positive whole number of elapsed days")
    return "1 day" if days == 1 else ("2-3 days" if days <= 3 else "4+ days")


def shock(change_percent, threshold):
    if not np.isfinite([change_percent, threshold]).all() or threshold < 0:
        raise ValueError("Invalid shock inputs")
    return bool(abs(change_percent) > threshold)


def make_policy(best):
    entries = []
    for row in best.sort_values(SERIES_FIELDS).to_dict("records"):
        method = row["baseline"]
        if method not in BASELINES:
            raise ValueError("Unrecognized baseline")
        window = int(method.rsplit("_", 1)[1]) if method.startswith("rolling_") else None
        entries.append({"series_id": row["series_id"], "identity": {k: row[k] for k in SERIES_FIELDS},
                        "selected_method": method, "window": window, "minimum_history": window or 1,
                        "fallback_method": "naive", "benchmark_mae": float(row["mae"]),
                        "evaluation_version": VERSION, "status": "selected"})
    return {"schema_version": 1, "evaluation_version": VERSION, "unit": "INR/quintal",
            "horizon": "next observed record", "selection_basis": "Retain Day 5 validation-selected per-series choices; no test-driven reselection",
            "ml_status": "experimental_not_selected", "fallback_status": "fallback",
            "unknown_identity": "unrecognized_series", "empty_history": "insufficient_history", "series": entries}


def validate_policy(policy):
    identities, ids = set(), set()
    if policy.get("schema_version") != 1 or not policy.get("series"):
        raise ValueError("Invalid policy schema")
    for entry in policy["series"]:
        identity = entry["identity"]
        if set(identity) != set(SERIES_FIELDS) or any(not isinstance(v, str) or not v for v in identity.values()):
            raise ValueError("Policy requires all six identity fields")
        key = tuple(identity[k] for k in SERIES_FIELDS)
        if key in identities or entry["series_id"] in ids:
            raise ValueError("Duplicate policy identity/ID")
        identities.add(key)
        ids.add(entry["series_id"])
        method = entry["selected_method"]
        if method not in BASELINES or entry["fallback_method"] != "naive":
            raise ValueError("Invalid policy method/fallback")
        expected = int(method.rsplit("_", 1)[1]) if method.startswith("rolling_") else None
        if entry["window"] != expected or entry["minimum_history"] != (expected or 1):
            raise ValueError("Policy history/window mismatch")
        if not np.isfinite(entry["benchmark_mae"]) or entry["benchmark_mae"] < 0:
            raise ValueError("Invalid benchmark MAE")
    return policy


def load_policy(path):
    return validate_policy(json.loads(path.read_text(encoding="utf-8")))


def policy_forecast(policy, identity, history):
    """History is a chronological exact-identity frame of completed observations only."""
    validate_policy(policy)
    entry = next((e for e in policy["series"] if e["identity"] == identity), None)
    if entry is None:
        return {"status": "unrecognized_series", "prediction": None, "method": None}
    if history.empty:
        return {"status": "insufficient_history", "prediction": None, "method": None}
    required = [*SERIES_FIELDS, "date", "modal_price"]
    if not set(required).issubset(history.columns) or not (history[SERIES_FIELDS] == pd.Series(identity)).all().all():
        raise ValueError("History must match all six policy identity fields")
    dates = pd.to_datetime(history.date, errors="raise")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("History dates must be unique and chronological")
    values = pd.to_numeric(history.modal_price, errors="coerce").to_numpy(dtype=float)
    valid = np.isfinite(values) & (values > 0)
    if not valid.any():
        return {"status": "insufficient_history", "prediction": None, "method": None}
    method = entry["selected_method"]
    needed = entry["minimum_history"]
    if len(values) < needed or not valid[-needed:].all():
        return {"status": "fallback", "prediction": float(values[valid][-1]), "method": "naive"}
    if method.startswith("historical_") and not valid.all():
        return {"status": "fallback", "prediction": float(values[valid][-1]), "method": "naive"}
    used = values[-needed:] if entry["window"] else values
    prediction = (values[-1] if method == "naive" else
                  np.median(used) if "median" in method else np.mean(used))
    return {"status": "selected", "prediction": float(prediction), "method": method}


def rolling_evaluation(frame, features, candidates, baseline, best, ml, selection):
    configurations = {c["id"]: c for c in CONFIGS}
    clean = pd.read_csv(ROOT / "data/processed/market_prices_clean.csv", parse_dates=["date"])
    rows, origins, thresholds = [], [], []
    for candidate in candidates.sort_values("series_id").to_dict("records"):
        sid = candidate["series_id"]
        identity = {k: candidate[k] for k in SERIES_FIELDS}
        group = frame.loc[frame.series_id.eq(sid)].sort_values("date")
        history = clean.loc[(clean[SERIES_FIELDS] == pd.Series(identity)).all(axis=1)].sort_values("date").reset_index(drop=True)
        if len(history) != candidate["observation_count"] or not (group[SERIES_FIELDS] == pd.Series(identity)).all().all():
            raise ValueError("Candidate history/identity mismatch")
        initial = history.loc[history.date.lt(group.loc[group.split.eq("validation"), "date"].min())]
        changes = initial.modal_price.pct_change().dropna().abs() * 100
        cutoff = float(changes.quantile(.95))
        q1, q2 = group.loc[group.split.eq("train"), "rolling_std_7"].quantile([1/3, 2/3]).tolist()
        thresholds.append({**identity, "series_id": sid, "shock_abs_percent_95": cutoff,
                           "volatility_q33": q1, "volatility_q67": q2, "threshold_history_end": initial.date.max().date().isoformat()})
        chosen = best.loc[best.series_id.eq(sid)].iloc[0].baseline
        config_id = selection.loc[selection.series_id.eq(sid)].iloc[0].config_id
        for window, past, block in windows(group):
            pipeline = make_pipeline(configurations[config_id], features)
            pipeline.fit(past[SERIES_FIELDS + features], past.modal_price)
            predicted = pipeline.predict(block[SERIES_FIELDS + features])
            origins.append({**identity, "series_id": sid, "window": window, "fit_rows": len(past),
                            "fit_end": past.date.max().date().isoformat(), "target_start": block.date.min().date().isoformat(),
                            "target_end": block.date.max().date().isoformat(), "target_count": len(block), "config_id": config_id})
            for (_, target), ml_prediction in zip(block.iterrows(), predicted):
                prior = history.loc[history.date.lt(target.date)]
                previous = float(prior.modal_price.iloc[-1])
                gap = int((target.date - prior.date.iloc[-1]).days)
                actual = float(target.modal_price)
                change = actual - previous
                predictions = forecast(prior.modal_price.to_numpy())
                saved = baseline.loc[baseline.series_id.eq(sid) & baseline.date.eq(target.date) & baseline.phase.eq("test")].set_index("baseline")
                for method, prediction in predictions.items():
                    np.testing.assert_allclose(prediction, saved.loc[method].predicted_modal_price, rtol=1e-10, atol=1e-9)
                original = ml.loc[ml.series_id.eq(sid) & ml.date.eq(target.date)].iloc[0]
                if window == 1:
                    np.testing.assert_allclose(ml_prediction, original.predicted_modal_price, rtol=1e-10, atol=1e-8)
                predictions.update(selected_baseline=predictions[chosen], ml_frozen=float(original.predicted_modal_price), ml_refit=float(ml_prediction))
                for method, prediction in predictions.items():
                    rows.append({**identity, "series_id": sid, "date": target.date.date().isoformat(), "window": window,
                                 "method": method, "selected_baseline": chosen, "ml_config": config_id,
                                 "actual": actual, "prediction": prediction, "absolute_error": abs(prediction - actual),
                                 "signed_error": prediction - actual, "previous_price": previous, "price_change": change,
                                 "absolute_percentage_change": abs(change / previous * 100), "gap_days": gap, "gap_band": gap_band(gap),
                                 "historical_volatility": float(target.rolling_std_7),
                                 "volatility_band": "low" if target.rolling_std_7 <= q1 else "medium" if target.rolling_std_7 <= q2 else "high",
                                 "shock": shock(change / previous * 100, cutoff), "shock_threshold": cutoff,
                                 "history_end": prior.date.max().date().isoformat(),
                                 "ml_fit_end": past.date.max().date().isoformat() if method == "ml_refit" else None})
    return pd.DataFrame(rows), pd.DataFrame(origins), pd.DataFrame(thresholds)


def grouped_metrics(frame, keys):
    return pd.DataFrame([{**dict(zip(keys, key if isinstance(key, tuple) else (key,))), "observations": len(group),
                          **error_metrics(group.actual, group.prediction)}
                         for key, group in frame.groupby(keys, sort=True)])


def figures(diagnostic, window_scores, stability):
    directory = ROOT / "reports/figures/evaluation"
    directory.mkdir(parents=True, exist_ok=True)
    outputs = []
    specifications = [
        ("01_temporal_mae.png", "window", "mae", "Three chronological blocks (20 observations per series)"),
        ("02_commodity_mae.png", "commodity", "mae", "Error by commodity on reused historical targets"),
        ("03_volatility_mae.png", "volatility_band", "mae", "Past-only volatility; initial-training thresholds"),
        ("04_gap_mae.png", "gap_band", "mae", "Elapsed reporting gaps; 4+ days has only 17 targets"),
        ("05_shock_mae.png", "shock", "mae", "Post-hoc shocks: movement above training 95th percentile"),
        ("06_bias.png", "commodity", "bias", "Signed error: positive means overprediction"),
    ]
    for name, dimension, metric, title in specifications:
        aggregate = grouped_metrics(diagnostic, [dimension, "method"])
        values = aggregate.pivot(index=dimension, columns="method", values=metric)
        if dimension == "volatility_band":
            values = values.reindex(["low", "medium", "high"])
        fig, ax = plt.subplots(figsize=(10, 5))
        values.plot.bar(ax=ax, rot=0, color=["#b07d27", "#c44c45", "#375f91"])
        ax.set(title=title, ylabel="INR / quintal", xlabel=dimension.replace("_", " "))
        ax.axhline(0, color="black", linewidth=.6)
        ax.legend(title="Method", fontsize=8)
        fig.tight_layout()
        path = directory / name
        fig.savefig(path, dpi=140)
        plt.close(fig)
        outputs.append(path)
    worst = diagnostic.loc[diagnostic.method.eq("selected_baseline")].nlargest(8, "absolute_error").copy()
    worst["label"] = worst.apply(lambda r: f"{r.market} | {r.commodity}\n{r.date}", axis=1)
    fig, ax = plt.subplots(figsize=(11, 6))
    ax.barh(worst.label[::-1], worst.absolute_error.iloc[::-1], color="#c44c45")
    ax.set(title="Largest selected-baseline misses; retained in evaluation", xlabel="Absolute error (INR / quintal)")
    fig.tight_layout()
    path = directory / "07_worst_misses.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    outputs.append(path)
    fig, ax = plt.subplots(figsize=(11, 7))
    subset = stability.loc[stability.method.isin(["selected_baseline", "ml_refit"])].copy()
    identities = subset.drop_duplicates("series_id").sort_values(SERIES_FIELDS)
    for method, offset, color in [("selected_baseline", -.16, "#375f91"), ("ml_refit", .16, "#c44c45")]:
        group = subset.loc[subset.method.eq(method)].set_index("series_id").loc[identities.series_id]
        ax.errorbar(group.mae_mean, np.arange(9) + offset,
                    xerr=np.vstack([group.mae_mean - group.mae_best, group.mae_worst - group.mae_mean]),
                    fmt="o", capsize=3, label=method, color=color)
    ax.set_yticks(np.arange(9), [f"{r.market} | {r.commodity} | {r.variety}" for r in identities.itertuples()], fontsize=8)
    ax.set(title="Window MAE: mean point and best-to-worst range\nAll series Gujarat / FAQ; ranges are not confidence intervals", xlabel="INR / quintal")
    ax.legend()
    fig.tight_layout()
    path = directory / "08_stability.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    outputs.append(path)
    return outputs


def run():
    summary_path = OUT / "robustness_summary.json"
    old = json.loads(summary_path.read_text(encoding="utf-8")) if summary_path.exists() else None
    if old:
        verify_hashes(old["output_sha256"])
        verify_hashes(old["protected_sha256"])
    audit, candidates, baseline, best, ml = reconstruct()
    frame, parts, features, metadata, protected = load_feature_inputs()
    previous = json.loads((OUT / "ml_summary.json").read_text(encoding="utf-8"))
    protected.update(previous["design"]["input_hashes"])
    protected.update(previous["output_sha256"])
    protected["reports/data/ml_summary.json"] = file_digest(OUT / "ml_summary.json")
    for directory in [ROOT / "data/raw", ROOT / "reports/data", ROOT / "reports/figures"]:
        for path in directory.rglob("*"):
            if path.is_file() and (directory.name == "raw" or path.name.startswith(("cleaning", "CLEANING", "eda", "EDA", "series_", "market_", "commodity_", "monthly_"))):
                protected[str(path.relative_to(ROOT))] = file_digest(path)
    verify_hashes(protected)
    selection = pd.DataFrame(json.loads((OUT / "ml_selection.json").read_text(encoding="utf-8"))["selection"])
    with threadpool_limits(limits=1):
        predictions, origins, thresholds = rolling_evaluation(frame, features, candidates, baseline, best, ml, selection)
    diagnostic = predictions.loc[predictions.method.isin(["selected_baseline", "ml_frozen", "ml_refit"])].copy()
    window_scores = grouped_metrics(predictions, [*SERIES_FIELDS, "series_id", "method", "window"])
    stability = window_scores.groupby([*SERIES_FIELDS, "series_id", "method"], as_index=False).agg(
        mae_mean=("mae", "mean"), mae_median=("mae", "median"), mae_std=("mae", lambda x: x.std(ddof=0)),
        mae_best=("mae", "min"), mae_worst=("mae", "max"))
    regimes = pd.concat([grouped_metrics(diagnostic, ["commodity", "method", field]).rename(columns={field: "regime"}).assign(dimension=field)
                         for field in ["shock", "gap_band", "volatility_band"]], ignore_index=True)
    family = diagnostic.merge(selection[["series_id", "model"]], on="series_id", validate="many_to_one")
    family_metrics = grouped_metrics(family, ["model", "method", "shock"])
    overall = grouped_metrics(diagnostic, ["method"])
    commodity = grouped_metrics(diagnostic, ["commodity", "method"])
    final_rows = []
    for sid, group in diagnostic.loc[diagnostic.method.eq("selected_baseline")].groupby("series_id"):
        chosen = best.loc[best.series_id.eq(sid)].iloc[0]
        stats = stability.loc[stability.series_id.eq(sid) & stability.method.eq("selected_baseline")].iloc[0]
        refit = diagnostic.loc[diagnostic.series_id.eq(sid) & diagnostic.method.eq("ml_refit")]
        original = diagnostic.loc[diagnostic.series_id.eq(sid) & diagnostic.method.eq("ml_frozen")]
        final_rows.append({**group.iloc[0][SERIES_FIELDS].to_dict(), "series_id": sid, "selected_method": chosen.baseline,
                           "benchmark_mae": float(chosen.mae), "robustness_mae": float(group.absolute_error.mean()),
                           "worst_window_mae": stats.mae_worst, "best_window_mae": stats.mae_best, "window_mae_std": stats.mae_std,
                           "bias": float(group.signed_error.mean()), "shock_mae": float(group.loc[group.shock, "absolute_error"].mean()) if group.shock.any() else None,
                           "normal_mae": float(group.loc[~group.shock, "absolute_error"].mean()),
                           "ml_frozen_mae": float(original.absolute_error.mean()), "ml_refit_mae": float(refit.absolute_error.mean()),
                           "status": "selected", "fallback": "naive", "recommendation": "retain_validation_selected_baseline"})
    final = pd.DataFrame(final_rows)
    policy_path = ROOT / "configs/forecast_policy.json"
    policy = validate_policy(make_policy(best))
    write_json(policy_path, policy)
    if load_policy(policy_path) != policy:
        raise ValueError("Policy reload differs")
    clean = pd.read_csv(ROOT / "data/processed/market_prices_clean.csv", parse_dates=["date"])
    for row in diagnostic.loc[diagnostic.method.eq("selected_baseline")].itertuples():
        identity = {k: getattr(row, k) for k in SERIES_FIELDS}
        history = clean.loc[(clean[SERIES_FIELDS] == pd.Series(identity)).all(axis=1) & clean.date.lt(pd.Timestamp(row.date))].sort_values("date")
        value = policy_forecast(load_policy(policy_path), identity, history)
        np.testing.assert_allclose(value["prediction"], row.prediction, atol=1e-9)
    worst = diagnostic.sort_values(["method", "absolute_error", "series_id", "date"], ascending=[True, False, True, True]).groupby("method").head(10)
    tables = {"local/robustness_predictions.csv": predictions, "robustness_origins.csv": origins,
              "robustness_thresholds.csv": thresholds, "robustness_window_metrics.csv": window_scores,
              "robustness_stability.csv": stability, "robustness_regime_metrics.csv": regimes,
              "robustness_family_metrics.csv": family_metrics, "robustness_commodity_metrics.csv": commodity,
              "robustness_final_evaluation.csv": final, "robustness_worst_errors.csv": worst}
    for name, content in tables.items():
        content.to_csv(OUT / name, index=False, float_format="%.15g", lineterminator="\n")
    figure_paths = figures(diagnostic, window_scores, stability)
    shocks = grouped_metrics(diagnostic, ["shock", "method"])
    gaps = grouped_metrics(diagnostic, ["gap_band", "method"])
    temporal = grouped_metrics(diagnostic, ["window", "method"])
    block_comparison = window_scores.loc[window_scores.method.isin(["selected_baseline", "ml_refit"])].pivot(
        index=["series_id", "window"], columns="method", values="mae")
    wins = window_scores.loc[window_scores.method.isin(BASELINES)].sort_values(["series_id", "window", "mae", "rmse", "method"]).groupby(["series_id", "window"]).head(1)
    wins.to_csv(OUT / "robustness_window_winners.csv", index=False, float_format="%.15g", lineterminator="\n")
    summary = {"evaluation_version": VERSION, "series_evaluated": 9, "methods_evaluated": sorted(predictions.method.unique().tolist()),
               "windows_per_series": 3, "origins": len(origins), "targets": 540, "prediction_rows": len(predictions),
               "design": "Three successive 20-record blocks within the existing 60-record test per series; frozen Day 7 configurations refit at each origin on own earlier feature rows. One-step features and baseline history update after each actual. No tuning or policy reselection.",
               "historical_reconstruction": audit, "overall_metrics": overall.to_dict("records"), "commodity_metrics": commodity.to_dict("records"),
               "shock_analysis": shocks.to_dict("records"), "gap_analysis": gaps.to_dict("records"), "temporal_metrics": temporal.to_dict("records"),
               "stability_table": "reports/data/robustness_stability.csv", "final_strategy": policy["selection_basis"],
               "benchmark_baseline_wins": int((final.benchmark_mae < final.ml_frozen_mae).sum()),
               "benchmark_ml_wins": int((final.ml_frozen_mae < final.benchmark_mae).sum()),
               "refit_baseline_wins": int((final.robustness_mae < final.ml_refit_mae).sum()),
               "refit_ml_wins": int((final.ml_refit_mae < final.robustness_mae).sum()),
               "refit_ml_block_wins": int((block_comparison.ml_refit < block_comparison.selected_baseline).sum()),
               "volatility_metrics": grouped_metrics(diagnostic, ["volatility_band", "method"]).to_dict("records"),
               "uncertainty": "Skipped: validation residuals already served method selection; no independent calibration period reserved. No claimed confidence bands.",
               "policy_path": "configs/forecast_policy.json", "policy_reload_verified_targets": 540,
               "protected_sha256": protected, "evaluation_code_sha256": file_digest(ROOT / "scripts/evaluate_robustness.py")}
    report_path = OUT / "ROBUSTNESS_EVALUATION_REPORT.md"
    report_path.write_text(report(summary, final, temporal, shocks, gaps, worst, wins), encoding="utf-8")
    artifacts = [policy_path, report_path, OUT / "robustness_window_winners.csv", *[OUT / n for n in tables], *figure_paths]
    summary["generated_files"] = [str(p.relative_to(ROOT)) for p in artifacts]
    summary["output_sha256"] = {str(p.relative_to(ROOT)): file_digest(p) for p in artifacts}
    verify_hashes(protected)
    if old and old["evaluation_code_sha256"] == summary["evaluation_code_sha256"]:
        if old != summary:
            raise ValueError("Rerun differs from existing Day 8 summary; inspect differences before replacing")
    write_json(summary_path, summary)
    print(json.dumps({k: summary[k] for k in ["series_evaluated", "targets", "origins", "overall_metrics", "refit_baseline_wins", "refit_ml_wins"]}, indent=2))
    return summary


def report(summary, final, temporal, shocks, gaps, worst, wins):
    show = lambda frame, columns: table(frame.round(3).to_dict("records"), columns)
    return "\n\n".join([
        "# Day 8 — Robust evaluation and final forecasting policy",
        "Krishkumar | Roll No: 2401CS83 | IIT Patna | https://github.com/Krish290107/agrisense",
        "## Objective and evidence boundary",
        "Carry forward a defensible strategy without optimizing against known test outcomes. All nine exact six-field identities remain separate. Day 5 and Day 7 dates were already examined during development: this is a reused historical benchmark, not a pristine holdout or independent replication. No significance or live-production guarantee is claimed.",
        "## Historical reconstruction",
        f"Independently reconstructed all 126 baseline metric rows, 7,560 baseline predictions and 540 ML predictions; MAE/RMSE/sMAPE agree within numerical tolerance. Baseline MAE {summary['historical_reconstruction']['baseline']['mae']:.3f}; original ML MAE {summary['historical_reconstruction']['ml']['mae']:.3f} INR/quintal. Baseline wins all nine series. Pooled RMSE favors original ML (225.505 versus 233.924), so lower MAE does not mean uniformly smaller tail loss. Equal series sizes make pooled MAE equal macro MAE; pooled RMSE differs from mean per-series RMSE.",
        "CSV reconstruction swaps ranks 4/5 for Bilimora Onion validation rolling_mean_7/rolling_median_5: their MAEs tie within 1e-9 INR. Raw floating-point tie ordering is not substantive evidence. Selected winners remain identical; historical ranks and files are preserved.",
        "## Chronological robustness design",
        summary["design"],
        "There are 27 fit origins (three per series), not 27 independent experiments. Blocks have different calendar boundaries across markets and are adjacent, dependent and small. No earlier origins were scored with configurations selected on later validation data. Initial TRAIN alone fixes each series' 95th percentile absolute percentage-change shock threshold and rolling_std_7 terciles. Shock is strict greater-than and post-hoc only; volatility uses seven past observations. Gap days are elapsed calendar days. All seven original baseline formulas are recomputed from original prior prices and checked against saved predictions. ml_frozen is the saved Day 7 prediction; ml_refit uses unchanged configuration refitted on expanded history at each block origin. No outcome at/after an origin enters that fit. No target-date feature is passed to ML. Earlier actuals within a block update features; this is not a 20-step forecast issued at one time.",
        show(temporal, ["window", "method", "observations", "mae", "rmse", "bias"]),
        "## Stability and policy decision",
        show(final, ["market", "commodity", "variety", "selected_method", "robustness_mae", "worst_window_mae", "window_mae_std", "ml_refit_mae"]),
        f"Against block-refitted ML, retained baselines have lower aggregate per-series MAE in {summary['refit_baseline_wins']}/9 series and ML in {summary['refit_ml_wins']}/9. These diagnostics do not authorize switching based on known test outcomes. Window winners are retrospective only (robustness_window_winners.csv); window mean, median, population SD, best and worst MAE for every method/identity are in robustness_stability.csv. Retain the original validation-selected policy because its overall MAE evidence, simplicity and interpretability remain preferable; individual wins and pooled RMSE differences do not establish a robust replacement rule.",
        f"Block-refitted ML wins {summary['refit_ml_block_wins']}/27 individual series-block comparisons, although baseline pooled MAE is lower in each of the three blocks. The first block is the hardest overall for the retained policy (MAE 134.643); the worst individual block is Navsari Tomato block 1 (450.000). Per-series baseline winners can change, so the selected method is not claimed optimal in every period.",
        "## Commodity, shocks, gaps and bias",
        show(pd.DataFrame(summary["commodity_metrics"]), ["commodity", "method", "mae", "bias", "over_rate", "under_rate"]),
        show(shocks, ["shock", "method", "observations", "mae", "rmse"]),
        show(gaps, ["gap_band", "method", "observations", "mae", "bias"]),
        "Across all commodities, 46/540 observations qualify as shocks. Their baseline MAE is 437.66 versus 89.93 on ordinary observations; these 8.5% of targets contribute about 31.2% of baseline absolute loss. Refitted ML reduces shock MAE to 393.61 but raises ordinary-period MAE to 111.86. Long-gap (4+ days) ML MAE is 298.81 versus baseline 347.90; this diagnostic improvement is based on only 17 targets, and no gap-switching hybrid is selected from test outcomes. Baseline error is not monotonically increasing between the first two gap buckets.",
        "For Tomato, 13 shocks have baseline MAE 848.08 versus 177.99 for 167 ordinary targets; refitted ML shock MAE is 682.02. Tomato baseline MAE increases from 207.10 for one-day gaps to 582.14 for 4+ days, but the latter contains just seven observations. Baselines retain lower overall Tomato MAE and lower error in all three historical-volatility bands. Overall mean signed error is +4.17 for baselines versus +25.14 for refitted ML; commodity-level biases differ and cancel in the aggregate.",
        "Tomato has the largest commodity MAE with available inputs; this does not prove inherent unpredictability or a causal explanation. Sharp movements and reporting gaps are associated diagnostics, not causes. Only 17 targets have gaps of four or more days; subgroup estimates are noisy and mixtures of different series. Commodity-specific shock/gap/volatility counts and errors are in robustness_regime_metrics.csv. Linear versus tree-family shock diagnostics appear in robustness_family_metrics.csv; model family is confounded with series and cannot be interpreted as a controlled family comparison. Over/under rates use a 1e-9 tolerance; exact/tolerance ties account for the remainder.",
        "## Largest misses",
        show(worst.loc[worst.method.eq("selected_baseline")].head(5), ["market", "commodity", "date", "actual", "prediction", "absolute_error", "previous_price", "price_change", "gap_days", "historical_volatility"]),
        "Rows are retained. The full worst-error table includes original and refitted ML. Shock classification uses target outcomes only for this diagnostic table, never for fitting or prediction.",
        "## Final policy and fallback",
        "configs/forecast_policy.json is derived from best_baselines.csv, not the prompt or test winners: seven naive series and two rolling_mean_7 series (Dahod Onion and Potato). It stores full identity, parameters, minimum history, benchmark MAE, version and status. The baseline policy is selected for the next project stage; ML remains experimental/not selected and all artifacts remain intact. A recognized rolling series with insufficient valid trailing history falls back to its last finite positive observation. No valid prior observation returns insufficient_history with null prediction. Unknown exact identity returns unrecognized_series. Mixed identities, duplicate/unsorted dates and invalid policy definitions raise errors. Missing/invalid prices are never fabricated or interpolated. Caller must supply only already observed history; this local helper is not an API or fixed-date forecast service.",
        "Reloaded JSON reproduces all 540 selected historical predictions. Only chronological existing candidate history is accepted. No zero-price placeholder is emitted.",
        "## Uncertainty", summary["uncertainty"],
        "## Limitations and Day 9 readiness",
        "Only roughly two source years and fewer than two years for individual series, irregular observations, nine retrospectively chosen strong candidates, previously examined tests, dependent small windows, abrupt shocks, unverified publication/revision timing and no weather/arrivals/demand inputs limit generalization. One-step next-observed-record prediction differs from a forecast for a specified future date. Historical performance does not guarantee live accuracy. Fresh later data and independent calibration are required before stronger deployment or interval claims. No UI, API, deployment or historical data changes are part of Day 8. Day 9 can persist market observations, forecasts, this policy and model/evaluation metadata.",
    ]) + "\n"


if __name__ == "__main__":
    if "--audit-only" in sys.argv:
        print(json.dumps(reconstruct()[0], indent=2))
    else:
        run()
