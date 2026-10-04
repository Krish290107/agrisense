"""Deterministic cleaning of provenance-verified historical project observations."""

from __future__ import annotations

import argparse
from decimal import Decimal, InvalidOperation
import json
import re
import sys
from pathlib import Path

import pandas as pd

from market_data_common import (CONFIG, ROOT, SERIES_FIELDS, PRICES, column_mapping,
                                csv_frames, file_digest, missing, project_path, write_json)
from profile_market_data import prepare_file

REQUIRED = ["date", *SERIES_FIELDS, *PRICES]
COLUMNS = [*REQUIRED, "price_unit", "source_sha256", "source_record"]
KEY = [*SERIES_FIELDS, "date"]
NUMBER = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?", re.ASCII)


def decimal_price(value):
    """Validate without binary-float rounding or changing valid price text."""
    text = str(value).strip()
    if not NUMBER.fullmatch(text):
        return None
    try:
        result = Decimal(text)
        return result if result.is_finite() else None
    except InvalidOperation:
        return None


def normalize(values):
    return values.astype(str).str.replace(r"\s+", " ", regex=True).str.strip()


def load_observations(raw_root):
    manifests = sorted((raw_root / "historical").glob("*/provenance.json"))
    if not manifests:
        raise ValueError("No historical bundles found. Run scripts/import_market_data.py first.")
    frames, sources, seen = [], [], set()
    state = CONFIG["scope_screening"]["required_state"]
    commodities = CONFIG["scope_screening"]["candidate_commodities"]
    for manifest in manifests:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        path = manifest.parent / "source.csv"
        sha = file_digest(path)
        if sha != meta["sha256"] or manifest.parent.name != sha:
            raise ValueError(f"SHA-256 provenance mismatch: {path}")
        if meta["kind"] != "historical" or sha in seen:
            raise ValueError("Duplicate bundle identity or non-historical input.")
        seen.add(sha)
        mapping = column_mapping(meta["original_headers"], meta["column_mapping"])
        absent = sorted(set(REQUIRED) - mapping.keys())
        if absent:
            raise ValueError(f"{meta['original_filename']}: missing required columns: {', '.join(absent)}. Obtain a complete export or correct its import mapping.")
        selected, offset = [], 0
        for chunk in csv_frames(path, meta["encoding"], meta["delimiter"]):
            if list(chunk.columns) != meta["original_headers"]:
                raise ValueError("Source headers differ from provenance; recheck imported files.")
            mask = (normalize(chunk[mapping["state"]]).eq(state)
                    & normalize(chunk[mapping["commodity"]]).isin(commodities))
            subset = chunk.loc[mask].copy()
            # One-based CSV record number, including the header, not physical line number.
            subset.index = subset.index + offset + 2
            selected.append(subset)
            offset += len(chunk)
        if offset != meta["row_count"] or file_digest(path) != sha:
            raise ValueError("Source count/hash changed while reading; no outputs written.")
        raw = pd.concat(selected)
        frame, _, _ = prepare_file(raw, {**meta, "row_count": len(raw)}, None)
        frame["source_record"] = raw.index
        frame["raw_values"] = [json.dumps(record, ensure_ascii=False, sort_keys=True)
                               for record in raw.to_dict(orient="records")]
        frames.append(frame)
        sources.append({"original_filename": meta["original_filename"], "sha256": sha,
                        "input_rows": offset, "selected_rows": len(frame),
                        "source_url": meta.get("source_url"), "price_unit": meta.get("price_unit")})
    return pd.concat(frames, ignore_index=True), sources


def date_range(frame):
    dates = frame["parsed_date"].dropna()
    return {"earliest": dates.min().date().isoformat() if len(dates) else None,
            "latest": dates.max().date().isoformat() if len(dates) else None}


def clean_observations(observations):
    frame = observations.copy().sort_values(["source_sha256", "source_record"], kind="stable").reset_index(drop=True)
    # All required categories stay distinct; missing identities are quarantined.
    for field in SERIES_FIELDS:
        frame[field] = normalize(frame[field].fillna(""))
    frame["date"] = frame["parsed_date"].dt.strftime("%Y-%m-%d").fillna("")
    frame["price_unit"] = frame["effective_price_unit"].fillna("")
    for field in PRICES:
        frame[field] = frame[field].astype(str).str.strip()
    prices = [[decimal_price(value) for value in row]
              for row in frame[PRICES].itertuples(index=False, name=None)]
    numeric = pd.Series([any(value is None for value in row) for row in prices], index=frame.index)
    nonpositive = pd.Series([any(value is not None and value <= 0 for value in row) for row in prices], index=frame.index)
    order = pd.Series([all(value is not None for value in row) and not row[0] <= row[1] <= row[2]
                       for row in prices], index=frame.index)
    flags = {
        "invalid_date": frame["parsed_date"].isna(),
        "missing_identity": pd.concat([missing(frame[field]) for field in SERIES_FIELDS], axis=1).any(axis=1),
        "invalid_numeric": numeric,
        "nonpositive_price": nonpositive,
        "invalid_price_order": order,
        "invalid_price_unit": ~frame["price_unit"].eq("INR/quintal") | frame["price_unit_declaration_conflict"],
    }
    # Detect conflicts BEFORE removing invalid observations or exact copies.
    # Reuse Day 2's conservative raw price/arrivals/unit payload signature.
    identifiable = ~flags["invalid_date"] & ~flags["missing_identity"]
    conflict = pd.Series(False, index=frame.index)
    business = frame.loc[identifiable]
    conflict.loc[business.index] = business.groupby(KEY, dropna=False)["payload_signature"].transform("nunique").gt(1)
    flags["conflicting_duplicate_key"] = conflict
    invalid = pd.DataFrame(flags).any(axis=1)
    # Raw duplicate includes all source fields. Only otherwise-valid copies count
    # as duplicate removals, so accounting categories remain disjoint.
    exact = frame["raw_signature"].duplicated() & ~invalid
    # Equivalent records from differing headers/unmapped fields may share a key.
    equivalent = pd.Series(False, index=frame.index)
    candidates = frame.loc[~invalid & ~exact]
    equivalent.loc[candidates.index] = candidates.duplicated(KEY)
    reasons = {**flags, "exact_duplicate": exact, "equivalent_duplicate_key": equivalent}
    frame["rejection_reason"] = [";".join(name for name, flag in reasons.items() if flag.loc[index]) for index in frame.index]
    rejected = frame.loc[frame["rejection_reason"].ne(""), [*COLUMNS, "rejection_reason", "raw_values"]]
    cleaned = frame.loc[frame["rejection_reason"].eq(""), COLUMNS].sort_values(KEY, kind="stable").reset_index(drop=True)
    kept = frame.loc[frame["rejection_reason"].eq("")]
    summary = {
        "schema_version": 1, "target": "modal_price", "price_unit": "INR/quintal",
        "input_rows": len(frame), "output_rows": len(cleaned), "removed_rows": len(rejected),
        "exact_duplicates_removed": int(exact.sum()),
        "equivalent_duplicate_keys_removed": int(equivalent.sum()),
        "invalid_dates": int(flags["invalid_date"].sum()),
        "missing_identity_rows": int(flags["missing_identity"].sum()),
        "invalid_numeric_rows": int(numeric.sum()), "nonpositive_price_rows": int(nonpositive.sum()),
        "price_order_violations": int(order.sum()), "invalid_price_rows": int((numeric | nonpositive | order).sum()),
        "invalid_price_unit_rows": int(flags["invalid_price_unit"].sum()),
        "conflicting_keys": len(frame.loc[conflict, KEY].drop_duplicates()),
        "rejected_rows": int(invalid.sum()),
        "series_count_before": len(frame[SERIES_FIELDS].drop_duplicates()),
        "series_count_after": len(cleaned[SERIES_FIELDS].drop_duplicates()),
        "date_range_before": date_range(frame), "date_range_after": date_range(kept),
        "observation_dates_after": int(kept["parsed_date"].nunique()),
        "rows_by_commodity": {str(k): int(v) for k, v in cleaned["commodity"].value_counts().sort_index().items()},
        "rows_by_grade": {str(k): int(v) for k, v in cleaned["grade"].value_counts().sort_index().items()},
        "accounting": "input_rows = output_rows + rejected_rows + exact_duplicates_removed + equivalent_duplicate_keys_removed; issue counts can overlap",
    }
    assert not cleaned.duplicated(KEY).any()
    assert len(frame) == len(cleaned) + len(rejected)
    return cleaned, rejected.reset_index(drop=True), summary


def run_cleaning(raw_root, processed, reports):
    raw_root, processed, reports = (Path(path).resolve() for path in (raw_root, processed, reports))
    for output in (processed, reports):
        if output == raw_root or raw_root in output.parents or output in raw_root.parents:
            raise ValueError("Output directories must be separate from raw inputs.")
    observations, sources = load_observations(raw_root)
    if observations.empty:
        raise ValueError("No observations match the configured state and commodities; check source coverage.")
    cleaned, rejected, summary = clean_observations(observations)
    if cleaned.empty:
        raise ValueError("All selected observations failed validation; inspect input provenance and prices.")
    processed.mkdir(parents=True, exist_ok=True)
    local = reports / "local"
    local.mkdir(parents=True, exist_ok=True)
    clean_path, rejected_path = processed / "market_prices_clean.csv", local / "rejected_rows.csv"
    cleaned.to_csv(clean_path, index=False, lineterminator="\n")
    rejected.to_csv(rejected_path, index=False, lineterminator="\n")
    summary.update({"source_rows": sum(source["input_rows"] for source in sources), "sources": sources,
                    "scope": {"state": CONFIG["scope_screening"]["required_state"],
                              "commodities": CONFIG["scope_screening"]["candidate_commodities"]},
                    "cleaned_sha256": file_digest(clean_path), "rejected_sha256": file_digest(rejected_path),
                    "rules": "Six-field series identity plus date; whitespace-only category normalization; no price correction, filling, aggregation, features or forecasts."})
    write_json(reports / "cleaning_summary.json", summary)
    report = ("# Day 3 cleaning report\n\n"
              "Krishkumar | 2401CS83 | IIT Patna\n\n"
              "Repository: https://github.com/Krish290107/agrisense\n\n"
              f"Scanned {summary['source_rows']:,} source rows; selected {len(observations):,} Gujarat Onion/Potato/Tomato rows. "
              f"Retained **{len(cleaned):,} observations in {summary['series_count_after']} separate series**.\n\n"
              f"Removed {len(rejected)} rows: {summary['rejected_rows']} quarantined, "
              f"{summary['exact_duplicates_removed']} exact duplicate copies and "
              f"{summary['equivalent_duplicate_keys_removed']} equivalent key copies. "
              f"Invalid price rows: {summary['invalid_price_rows']}; conflicting keys: {summary['conflicting_keys']}. "
              "Issue counts may overlap; see cleaning_summary.json for complete accounting.\n\n"
              f"Cleaned dates: {summary['date_range_after']['earliest']} through {summary['date_range_after']['latest']}.\n\n"
              "Canonical CSV: `data/processed/market_prices_clean.csv`. Local audit: `reports/data/local/rejected_rows.csv`, "
              "including original field values, source hash, CSV record number and all rejection reasons. "
              "Valid price text is retained without floating-point rounding. Unit INR/quintal comes from imported source provenance.\n\n"
              "Whitespace is normalized; spelling, case, markets, districts, varieties and FAQ/Non-FAQ remain distinct. "
              "No missing dates or prices are filled. Source files are hash-verified and never written. "
              "All valid scoped observations are retained, not only the provisional Day 2 recommendation.\n\n"
              "Cleaning does not establish forecasting eligibility: short/sparse series, unverified label equivalence, "
              "absent arrivals and incomplete two-year same-series history remain limitations. "
              "The Day 2 profile remains an unchanged raw-data baseline. No features or models are generated.\n")
    (reports / "CLEANING_REPORT.md").write_text(report, encoding="utf-8", newline="\n")
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-root", default="data/raw")
    args = parser.parse_args()
    try:
        result = run_cleaning(project_path(args.raw_root), ROOT / "data/processed", ROOT / "reports/data")
    except (ValueError, OSError, KeyError) as exc:
        print(f"Cleaning failed: {exc}", file=sys.stderr)
        return 1
    print(f"Selected {result['input_rows']:,}; rejected {result['rejected_rows']}; exact duplicates {result['exact_duplicates_removed']}; cleaned {result['output_rows']:,}; series {result['series_count_after']}.")
    print("Dataset: data/processed/market_prices_clean.csv; summary: reports/data/cleaning_summary.json; report: reports/data/CLEANING_REPORT.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
