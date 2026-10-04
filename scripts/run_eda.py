"""Read-only EDA and historical forecasting-readiness assessment."""

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

from clean_market_data import COLUMNS, KEY, decimal_price
from market_data_common import CONFIG, ROOT, SERIES_FIELDS, PRICES, digest, file_digest, missing, write_json

POLICY = {
    "eligible": {"observations": 365, "span_days": 600, "density": .5, "max_gap_days": 45, "recency_days": 60},
    "limited": {"observations": 90, "span_days": 180, "density": .25, "max_gap_days": 90, "recency_days": 180},
}
COLORS = {"Onion": "#375f91", "Potato": "#b07d27", "Tomato": "#c44c45"}
FIGURES = ["01_commodity_observations.png", "02_price_distributions.png", "03_monthly_prices.png",
           "04_monthly_observations.png", "05_series_coverage.png", "06_gaps_and_history.png",
           "07_representative_series.png", "08_market_coverage.png", "09_readiness.png", "10_price_spreads.png"]


def validate_dataset(frame):
    absent = sorted(set(COLUMNS) - set(frame.columns))
    if absent:
        raise ValueError(f"Cleaned dataset missing columns: {', '.join(absent)}; rerun Day 3.")
    if frame.empty:
        raise ValueError("Cleaned dataset is empty.")
    if any(missing(frame[field]).any() for field in SERIES_FIELDS):
        raise ValueError("Missing series identity; rerun Day 3.")
    if not frame["date"].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
        raise ValueError("Dates must use YYYY-MM-DD; EDA does not clean dates.")
    dates = pd.to_datetime(frame["date"], format="%Y-%m-%d", errors="coerce")
    if dates.isna().any():
        raise ValueError("Invalid observation dates; rerun Day 3.")
    if frame.duplicated(KEY).any():
        raise ValueError("Duplicate series/date keys; rerun Day 3.")
    scope = CONFIG["scope_screening"]
    if set(frame.state) != {scope["required_state"]} or set(frame.commodity) != set(scope["candidate_commodities"]):
        raise ValueError("Unexpected state/commodity scope; inspect Day 3 output.")
    if not frame.price_unit.eq("INR/quintal").all():
        raise ValueError("Unexpected price units.")
    for values in frame[PRICES].itertuples(index=False, name=None):
        prices = [decimal_price(value) for value in values]
        if any(value is None for value in prices) or not 0 < prices[0] <= prices[1] <= prices[2]:
            raise ValueError("Invalid prices; EDA will not correct Day 3 output.")
    result = frame.copy()
    result["date"] = dates
    for field in PRICES:
        result[field] = pd.to_numeric(result[field], errors="coerce")
        if not np.isfinite(result[field]).all():
            raise ValueError("Prices exceed finite analytical precision.")
    return result.sort_values(KEY, kind="stable").reset_index(drop=True)


def statistics(values):
    return {"count": int(values.count()), "mean": float(values.mean()), "median": float(values.median()),
            "std": float(values.std()) if len(values) > 1 else None, "min": float(values.min()),
            "q25": float(values.quantile(.25)), "q75": float(values.quantile(.75)), "max": float(values.max())}


def readiness(metrics):
    def failures(rule):
        return [name for name, failed in {
            "short_observation_history": metrics["observation_count"] < rule["observations"],
            "short_calendar_span": metrics["span_days"] < rule["span_days"],
            "low_density": metrics["coverage_ratio"] < rule["density"],
            "large_internal_gap": metrics["max_gap_days"] > rule["max_gap_days"],
            "stale_at_dataset_end": metrics["recency_days"] > rule["recency_days"],
        }.items() if failed]
    strict = failures(POLICY["eligible"])
    if not strict:
        return "eligible", "meets_historical_baseline_screen"
    if not failures(POLICY["limited"]):
        return "limited", ";".join(strict)
    return "insufficient", ";".join(failures(POLICY["limited"]))


def analyze(frame):
    frame = frame.copy()
    frame["price_spread"] = frame.max_price - frame.min_price
    frame["month"] = frame.date.dt.strftime("%Y-%m")
    end = frame.date.max()
    rows, outliers, monthly_series = [], [], []
    for identity, group in frame.groupby(SERIES_FIELDS, sort=True):
        labels = dict(zip(SERIES_FIELDS, identity))
        sid = digest(json.dumps(labels, sort_keys=True).encode())[:16]
        dates = group.date.sort_values()
        gaps = dates.diff().dt.days.dropna() - 1
        span = (dates.max() - dates.min()).days + 1
        prices = group.modal_price
        q25, q75 = prices.quantile([.25, .75])
        iqr = float(q75 - q25)
        lower, upper = float(q25 - 3 * iqr), float(q75 + 3 * iqr)
        screenable = len(group) >= 30 and iqr > 0
        flags = (prices.lt(lower) | prices.gt(upper)) if screenable else pd.Series(False, index=group.index)
        item = {**labels, "series_id": sid, "observation_count": len(group),
                "first_date": dates.min().date().isoformat(), "last_date": dates.max().date().isoformat(),
                "span_days": span, "distinct_dates": int(dates.nunique()), "coverage_ratio": len(group) / span,
                "median_gap_days": float(gaps.median()) if len(gaps) else None,
                "max_gap_days": int(gaps.max()) if len(gaps) else 0,
                "missing_calendar_days": span - len(group), "recency_days": int((end - dates.max()).days),
                "observed_months": int(group.month.nunique()), "modal_median": float(prices.median()),
                "modal_std": float(prices.std()) if len(group) > 1 else None,
                "modal_iqr": iqr, "modal_cv": float(prices.std() / prices.mean()) if len(group) > 1 else None,
                "outlier_screened": screenable, "outlier_count": int(flags.sum())}
        item["readiness_status"], item["readiness_reason"] = readiness(item)
        rows.append(item)
        if flags.any():
            flagged = group.loc[flags, [*COLUMNS]].copy()
            flagged["series_id"] = sid
            flagged["lower_fence"] = lower
            flagged["upper_fence"] = upper
            outliers.append(flagged)
        for month, subset in group.groupby("month", sort=True):
            monthly_series.append({**labels, "series_id": sid, "month": month, "observations": len(subset),
                                   "median_modal_price": float(subset.modal_price.median()),
                                   "q25": float(subset.modal_price.quantile(.25)), "q75": float(subset.modal_price.quantile(.75))})
    series = pd.DataFrame(rows)
    ranked = series.loc[series.readiness_status.eq("eligible")].sort_values(
        ["commodity", "coverage_ratio", "observation_count", "recency_days", "max_gap_days", *SERIES_FIELDS],
        ascending=[True, False, False, True, True, *([True] * len(SERIES_FIELDS))], kind="stable")
    candidates = ranked.groupby("commodity", sort=True).head(3).reset_index(drop=True)
    monthly = frame.groupby(["commodity", "month"], sort=True).agg(
        observations=("modal_price", "size"), median_modal_price=("modal_price", "median"),
        q25=("modal_price", lambda x: x.quantile(.25)), q75=("modal_price", lambda x: x.quantile(.75)),
        median_spread=("price_spread", "median")).reset_index()
    market_rows = []
    for identity, group in frame.groupby(SERIES_FIELDS[:3], sort=True):
        subset = series.loc[(series[SERIES_FIELDS[:3]] == identity).all(axis=1)]
        market_rows.append(dict(zip(SERIES_FIELDS[:3], identity)) | {
            "observations": len(group), "commodities": int(group.commodity.nunique()),
            "series_count": len(subset), "first_date": group.date.min().date().isoformat(),
            "last_date": group.date.max().date().isoformat(), "distinct_dates": int(group.date.nunique()),
            "span_days": int((group.date.max() - group.date.min()).days + 1),
            "eligible_series": int(subset.readiness_status.eq("eligible").sum()),
            "median_modal_price": float(group.modal_price.median()), "median_spread": float(group.price_spread.median())})
    markets = pd.DataFrame(market_rows).sort_values(["observations", "district", "market"], ascending=[False, True, True])
    market_prices = frame.groupby([*SERIES_FIELDS[:3], "commodity"], sort=True).agg(
        observations=("modal_price", "size"), median_modal_price=("modal_price", "median"),
        q25=("modal_price", lambda x: x.quantile(.25)), q75=("modal_price", lambda x: x.quantile(.75)),
        median_spread=("price_spread", "median")).reset_index()
    flagged = pd.concat(outliers, ignore_index=True) if outliers else pd.DataFrame(columns=[*COLUMNS, "series_id", "lower_fence", "upper_fence"])
    commodity = {}
    for name, group in frame.groupby("commodity", sort=True):
        months = monthly.loc[monthly.commodity.eq(name)]
        low = months.loc[months.median_modal_price.idxmin()]
        high = months.loc[months.median_modal_price.idxmax()]
        commodity[name] = {"rows": len(group), "markets": len(group[SERIES_FIELDS[:3]].drop_duplicates()),
                           "series": int(series.commodity.eq(name).sum()), "distinct_dates": int(group.date.nunique()),
                           "first_date": group.date.min().date().isoformat(), "last_date": group.date.max().date().isoformat(),
                           "modal_price": statistics(group.modal_price), "price_spread": statistics(group.price_spread),
                           "pooled_monthly_low": {"month": low.month, "median": float(low.median_modal_price)},
                           "pooled_monthly_high": {"month": high.month, "median": float(high.median_modal_price)},
                           "outlier_rows": int(flagged.commodity.eq(name).sum())}
    summary = {"schema_version": 1, "rows": len(frame), "date_range": {"first": frame.date.min().date().isoformat(), "last": end.date().isoformat()},
               "distinct_dates": int(frame.date.nunique()), "districts": int(frame.district.nunique()),
               "markets": len(markets), "market_definition": "state + district + market", "commodities": commodity,
               "varieties": int(frame.variety.nunique()), "grades": int(frame.grade.nunique()), "total_series": len(series),
               "observations_per_grade": {str(k): int(v) for k, v in frame.grade.value_counts().sort_index().items()},
               "coverage": {field: statistics(series[field]) for field in ["observation_count", "span_days", "coverage_ratio", "max_gap_days", "recency_days"]},
               "gap_definition": "Missing calendar days strictly between consecutive observations; singleton maximum is 0 and median is null; no inserted observations.",
               "readiness_policy": POLICY, "recency_reference": end.date().isoformat(),
               "readiness_counts": {status: int(series.readiness_status.eq(status).sum()) for status in POLICY.keys() | {"insufficient"}},
               "recency_sensitivity": {str(days): int(((series.observation_count >= 365) & (series.span_days >= 600) & (series.coverage_ratio >= .5) & (series.max_gap_days <= 45) & (series.recency_days <= days)).sum()) for days in [30, 60, 90]},
               "outliers": {"method": "Within-series outer fences Q1-3*IQR / Q3+3*IQR; minimum 30 observations and positive IQR; descriptive full-history screen only",
                            "flagged_rows": len(flagged), "affected_series": int(flagged.series_id.nunique()),
                            "screened_series": int(series.outlier_screened.sum()), "unscreened_series": int((~series.outlier_screened).sum())},
               "candidate_ranking": "Eligible only; per commodity: density descending, observations descending, recency ascending, max gap ascending, then full identity; top three each",
               "selected_candidates": json.loads(candidates.to_json(orient="records")), "figures": FIGURES}
    summary["readiness_counts"] = {key: summary["readiness_counts"][key] for key in ["eligible", "limited", "insufficient"]}
    return frame, series, candidates, monthly, pd.DataFrame(monthly_series), markets, market_prices, flagged, summary


def label(row):
    return f"{row['district']} / {row['market']} | {row['commodity']} | {row['variety']} | {row['grade']}"


def make_figures(frame, series, candidates, monthly, markets, figures):
    figures.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "axes.grid": True, "grid.alpha": .18,
                         "figure.facecolor": "white", "savefig.facecolor": "white"})
    names = sorted(COLORS)
    colors = [COLORS[name] for name in names]

    def save(fig, number):
        fig.savefig(figures / FIGURES[number - 1], dpi=140, metadata={"Software": "AgriSense Day 4"})
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    counts = frame.commodity.value_counts().reindex(names)
    bars = ax.bar(names, counts, color=colors)
    ax.bar_label(bars, fmt="{:,.0f}", padding=4)
    ax.set(title="Cleaned observations by commodity", ylabel="Observation rows", ylim=(0, counts.max() * 1.15))
    save(fig, 1)

    fig, axes = plt.subplots(1, 2, figsize=(12, 5), layout="constrained")
    for name in names:
        axes[0].hist(frame.loc[frame.commodity.eq(name), "modal_price"], bins=np.linspace(0, frame.modal_price.max(), 45),
                     histtype="step", linewidth=1.7, density=True, label=name, color=COLORS[name])
    axes[0].legend()
    axes[0].set(xlabel="Modal price (INR/quintal)", ylabel="Probability density")
    axes[1].boxplot([frame.loc[frame.commodity.eq(name), "modal_price"] for name in names], tick_labels=names,
                    flierprops={"markersize": 2, "alpha": .25})
    axes[1].set(ylabel="Modal price (INR/quintal)", ylim=(0, None))
    fig.suptitle("Price distributions — pooled markets/varieties/grades; box whiskers: 1.5 × IQR")
    save(fig, 2)

    fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True, layout="constrained")
    for ax, name in zip(axes, names):
        group = monthly.loc[monthly.commodity.eq(name)]
        x = pd.to_datetime(group.month)
        ax.plot(x, group.median_modal_price, color=COLORS[name], label=f"{name}: median")
        ax.fill_between(x, group.q25, group.q75, color=COLORS[name], alpha=.2, label="25–75% interval")
        ax.set(ylabel="INR/quintal", ylim=(0, None))
        ax.legend(loc="upper left", ncols=2)
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.suptitle("Monthly prices — pooled descriptive medians, not forecasting series")
    save(fig, 3)

    fig, ax = plt.subplots(figsize=(11, 5), layout="constrained")
    for name in names:
        group = monthly.loc[monthly.commodity.eq(name)]
        ax.plot(pd.to_datetime(group.month), group.observations, marker=".", label=name, color=COLORS[name])
    ax.set(title="Monthly observation counts — changing pooled reporting coverage", ylabel="Observation rows", ylim=(0, None))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.legend()
    save(fig, 4)

    top = series.sort_values(["observation_count", "series_id"], ascending=[False, True]).head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(14, 7), layout="constrained")
    ax.barh([label(row) for row in top.to_dict("records")], top.observation_count, color=[COLORS[name] for name in top.commodity])
    ax.tick_params(axis="y", labelsize=8)
    ax.set(title="Most observed individual series — Gujarat", xlabel="Observed days (not calendar span)")
    save(fig, 5)

    fig, axes = plt.subplots(1, 2, figsize=(11, 5), layout="constrained")
    for ax, values, edges, labels, color, title, xlabel in [
        (axes[0], series.observation_count, [0, 30, 90, 180, 365, 500, np.inf],
         ["1–29", "30–89", "90–179", "180–364", "365–499", "500+"], "#375f91", "History is highly uneven", "Observation-count category"),
        (axes[1], series.max_gap_days, [0, 1, 8, 16, 31, 61, 121, np.inf],
         ["0", "1–7", "8–15", "16–30", "31–60", "61–120", "121+"], "#b07d27", "Internal gaps (singletons have 0)", "Maximum missing-calendar-day category"),
    ]:
        counts = pd.cut(values, bins=edges, labels=labels, right=False).value_counts(sort=False)
        ax.bar(counts.index.astype(str), counts, color=color)
        ax.set(xlabel=xlabel, ylabel="Series", title=title)
        ax.tick_params(axis="x", rotation=30)
    save(fig, 6)

    representatives = candidates.groupby("commodity", sort=True).head(1)
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    for ax, name in zip(axes, names):
        choice = representatives.loc[representatives.commodity.eq(name)]
        if choice.empty:
            ax.text(.5, .5, f"{name}: no eligible series", ha="center", transform=ax.transAxes)
            continue
        row = choice.iloc[0]
        group = frame.loc[(frame[SERIES_FIELDS] == row[SERIES_FIELDS]).all(axis=1)]
        ax.scatter(group.date, group.modal_price, s=5, color=COLORS[name])
        ax.set(title=label(row), ylabel="INR/quintal", ylim=(0, None))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    fig.suptitle("Representative eligible series — observed points only; no gap filling")
    save(fig, 7)

    top = markets.head(12).iloc[::-1]
    fig, ax = plt.subplots(figsize=(11, 7), layout="constrained")
    ax.barh(top.district + " / " + top.market, top.observations, color="#375f91")
    ax.set(title="Market coverage — pooled counts across commodities/varieties/grades", xlabel="Observation rows")
    ax.tick_params(axis="y", labelsize=9)
    save(fig, 8)

    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    counts = series.readiness_status.value_counts().reindex(["eligible", "limited", "insufficient"], fill_value=0)
    bars = ax.bar(counts.index, counts, color=["#43856a", "#b07d27", "#9a6872"])
    ax.bar_label(bars, padding=4)
    ax.set(title="Historical baseline readiness — not live forecasting approval", ylabel="Series", ylim=(0, max(counts) * 1.15))
    save(fig, 9)

    fig, ax = plt.subplots(figsize=(9, 5), layout="constrained")
    ax.boxplot([frame.loc[frame.commodity.eq(name), "price_spread"] for name in names], tick_labels=names,
               flierprops={"markersize": 2, "alpha": .25})
    ax.set(title="Price spreads — pooled; box whiskers: 1.5 × IQR", ylabel="Max − min price (INR/quintal)", ylim=(0, None))
    save(fig, 10)


def table(records, columns):
    return "\n".join(["| " + " | ".join(columns) + " |", "| " + " | ".join(["---"] * len(columns)) + " |"] +
                     ["| " + " | ".join(str(row.get(column, "")).replace("|", "/") for column in columns) + " |" for row in records])


def report(summary, series, candidates, markets, flagged):
    s = summary
    commodity_rows = [{"Commodity": name, "Rows": v["rows"], "Markets": v["markets"], "Series": v["series"],
                       "Median": v["modal_price"]["median"], "IQR": v["modal_price"]["q75"] - v["modal_price"]["q25"],
                       "Std": round(v["modal_price"]["std"], 1), "Median spread": v["price_spread"]["median"]} for name, v in s["commodities"].items()]
    strongest = [{"Series (Gujarat)": label(row), "Days": row["observation_count"], "Span": row["span_days"],
                  "Density": f"{row['coverage_ratio']:.1%}", "Max gap": row["max_gap_days"], "Last": row["last_date"]} for row in candidates.to_dict("records")]
    text = ["# Day 4: EDA and historical forecasting readiness", "Krishkumar | 2401CS83 | IIT Patna\n\nRepository: https://github.com/Krish290107/agrisense",
            "## Dataset and integrity", f"{s['rows']:,} observations; {s['total_series']} exact six-field series; {s['markets']} district-market combinations; {s['districts']} districts; {s['varieties']} varieties; {s['grades']} grades. Dates: {s['date_range']['first']}–{s['date_range']['last']} across {s['distinct_dates']} observed dates. Modal price is the future target, in INR/quintal. Input hash matches the Day 3 summary. Date/identity/price/unit/duplicate checks pass; EDA never rewrites inputs.",
            "## Commodity prices", table(commodity_rows, ["Commodity", "Rows", "Markets", "Series", "Median", "IQR", "Std", "Median spread"]),
            "All price statistics above are pooled observation-weighted descriptions: markets, varieties and grades differ. They are not comparable investment returns or Gujarat-wide forecast targets. Full count/mean/median/std/min/quartile/max statistics are in eda_summary.json. Series-relative IQR/CV are in series_readiness.csv; singleton standard deviation/CV is undefined, not zero.",
            "## Monthly patterns and coverage composition"]
    for name, item in s["commodities"].items():
        low, high = item["pooled_monthly_low"], item["pooled_monthly_high"]
        text.append(f"- {name}: pooled monthly median low {low['median']:,.1f} in {low['month']}; high {high['median']:,.1f} in {high['month']}. {item['distinct_dates']} distinct observed dates; {item['outlier_rows']} series-relative flags.")
    text += ["Monthly medians and IQR bands show observed variation, not established long-term seasonality. Approximately two source years, changing market/grade mix and incomplete series histories confound pooled comparisons. series_monthly.csv permits same-identity checks; no month-of-year average is treated as a seasonal model.",
             "## Markets and series coverage", table(markets.head(8).to_dict("records"), ["district", "market", "observations", "commodities", "eligible_series", "span_days"]),
             "Market counts/spans above pool separate identities and do not imply continuous forecasting history. market_summary.csv includes all markets (including sparse ones); market_commodity_prices.csv compares median/IQR/spread by commodity, still pooling varieties/grades. Rank individual series using series_readiness.csv.",
             "Longest pooled market spans: " + "; ".join(f"{r['district']} / {r['market']}: {r['span_days']} days" for r in markets.sort_values(["span_days", "district", "market"], ascending=[False, True, True]).head(3).to_dict("records")) + ". Sparse markets: " + "; ".join(f"{r['district']} / {r['market']}: {r['observations']} rows" for r in markets.sort_values(["observations", "district", "market"]).head(3).to_dict("records")) + ".",
             f"Median series: {s['coverage']['observation_count']['median']:g} observations, {s['coverage']['span_days']['median']:g}-day span, {s['coverage']['coverage_ratio']['median']:.1%} density. Maximum history is {int(s['coverage']['span_days']['max'])} days; no full two-year same-series history. Median of series maximum gaps is {s['coverage']['max_gap_days']['median']:g} days; largest internal gap is {int(s['coverage']['max_gap_days']['max'])} missing calendar days. Gaps may be closures or non-reporting. Singleton density can be 100% and maximum gap 0, so density alone is not readiness.",
             "## Readiness criteria and candidates", "Eligible: at least 365 observations, 600-day span, 50% density, maximum 45-day internal missing gap, and last observation within 60 days of dataset end. Limited: at least 90 observations, 180-day span, 25% density, maximum 90-day gap and recency within 180 days, but fails eligible criteria. Otherwise insufficient. These are screening choices, not accuracy guarantees.",
             f"The distribution supports reusing Day 2's explicitly shorter-history screen: median count is only {s['coverage']['observation_count']['median']:g}, while the upper quartile is {s['coverage']['observation_count']['q75']:g}. Recency sensitivity with the other eligible thresholds fixed: 30 days → {s['recency_sensitivity']['30']}, 60 → {s['recency_sensitivity']['60']}, 90 → {s['recency_sensitivity']['90']}. The 60-day choice accommodates the observed late-2025 reporting change without merging labels. Recency reference is {s['recency_reference']}, not today's date; this dataset does not authorize live predictions.",
             f"Readiness: **{s['readiness_counts']['eligible']} eligible, {s['readiness_counts']['limited']} limited, {s['readiness_counts']['insufficient']} insufficient**. Each row has explicit reasons. Eligible counts leave room for chronological evaluation, but calendar-aligned horizons and actual split feasibility still require Day 5 checks; no splits/features were made today.",
             table(strongest, ["Series (Gujarat)", "Days", "Span", "Density", "Max gap", "Last"]),
             "Candidate selection: up to three per commodity, ranked by density, observation count, recency, gap then exact identity, using eligible rows only. These are historical baseline candidates; do not extrapolate across stale endpoints or relabeled markets.",
             "## Variability, spreads and unusual observations",
             f"Series-relative outer IQR fences flagged {s['outliers']['flagged_rows']} observations in {s['outliers']['affected_series']} series; {s['outliers']['screened_series']} series had ≥30 observations and positive IQR, while {s['outliers']['unscreened_series']} were not screened. These are unusual values, not proven errors; nothing is deleted. Full-history descriptive thresholds must not be reused as training-time features or preprocessing rules. Local flagged rows retain exact identities and source references."]
    variable = series.loc[series.observation_count.ge(90)].sort_values(["modal_cv", "series_id"], ascending=[False, True]).head(3)
    text.append(table([{"Series": label(r), "CV": round(r["modal_cv"], 3), "IQR": r["modal_iqr"]} for r in variable.to_dict("records")], ["Series", "CV", "IQR"]))
    if len(flagged):
        examples = flagged.sort_values(["modal_price", *KEY], ascending=[False, *([True] * len(KEY))]).head(3)
        text.append(table([{"Series": label(r), "Date": str(r["date"])[:10], "Modal": r["modal_price"]} for r in examples.to_dict("records")], ["Series", "Date", "Modal"]))
    text += ["Price spread (max minus min) is descriptive only; commodity/market/monthly spread summaries are supplied. Large spreads and CV may reflect market composition or genuine movements. No same-day min/max/spread is proposed as a future forecasting feature. Standard boxplot whiskers use 1.5×IQR and their dots differ from the stricter within-series 3×IQR audit flags.",
             "## Figures", *[f"![{name[3:-4].replace('_', ' ')}](../figures/{name})" for name in FIGURES],
             "## Limits and Day 5 handoff", "Preserve every district, market, commodity, variety and grade; FAQ and Non-FAQ remain separate. Missing dates are not zero prices and are never filled. Arrivals are absent. Label changes are not verified equivalences. All findings are retrospective; outlier fences and candidate selection use the available full history, so later evaluation must disclose this selection and fit any model/preprocessing only on its training window. Day 5 should compare simple chronological baselines on the candidate series, define observation-step versus calendar-day horizons explicitly, and verify usable holdout coverage before scoring."]
    return "\n\n".join(text) + "\n"


def run_eda(input_path, cleaning_summary, output, figures):
    input_path, cleaning_summary, output, figures = [Path(p).resolve() for p in (input_path, cleaning_summary, output, figures)]
    for destination in (output, figures):
        for protected in (ROOT / "data/raw", ROOT / "data/processed"):
            if destination == protected or protected in destination.parents:
                raise ValueError("EDA outputs must not be inside raw or processed data directories.")
    checksum = file_digest(input_path)
    cleaning = json.loads(cleaning_summary.read_text(encoding="utf-8"))
    if checksum != cleaning["cleaned_sha256"]:
        raise ValueError("Cleaned dataset hash differs from Day 3 summary; rerun/verify Day 3 first.")
    frame = validate_dataset(pd.read_csv(input_path, dtype=str, keep_default_na=False))
    if len(frame) != cleaning["output_rows"] or len(frame[SERIES_FIELDS].drop_duplicates()) != cleaning["series_count_after"]:
        raise ValueError("Cleaned row/series counts differ from Day 3.")
    frame, series, candidates, monthly, series_monthly, markets, market_prices, flagged, summary = analyze(frame)
    summary["input_sha256"] = checksum
    summary["software"] = {"pandas": pd.__version__, "numpy": np.__version__, "matplotlib": matplotlib.__version__}
    output.mkdir(parents=True, exist_ok=True)
    (output / "local").mkdir(exist_ok=True)
    for filename, data in [("series_readiness.csv", series), ("forecast_candidates.csv", candidates),
                            ("monthly_summary.csv", monthly), ("series_monthly.csv", series_monthly),
                            ("market_summary.csv", markets), ("market_commodity_prices.csv", market_prices),
                            ("local/eda_outliers.csv", flagged)]:
        data.to_csv(output / filename, index=False, lineterminator="\n", float_format="%.10g")
    make_figures(frame, series, candidates, monthly, markets, figures)
    write_json(output / "eda_summary.json", summary)
    (output / "EDA_REPORT.md").write_text(report(summary, series, candidates, markets, flagged), encoding="utf-8", newline="\n")
    if file_digest(input_path) != checksum:
        raise ValueError("Input changed during EDA; outputs must be regenerated from a stable input.")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    try:
        summary = run_eda(ROOT / "data/processed/market_prices_clean.csv", ROOT / "reports/data/cleaning_summary.json",
                          ROOT / "reports/data", ROOT / "reports/figures")
    except (ValueError, OSError, KeyError) as exc:
        print(f"EDA failed: {exc}", file=sys.stderr)
        return 1
    print(f"Analyzed {summary['rows']:,} rows, {summary['total_series']} series, {summary['markets']} markets; readiness {summary['readiness_counts']}.")
    print(f"Generated {len(FIGURES)} figures in reports/figures; report: reports/data/EDA_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
