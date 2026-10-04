"""Inspect imported CSV bundles without cleaning or modifying observations."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from market_data_common import (CONFIG, NUMERIC_FIELDS, PRICES, ROOT, SERIES_FIELDS,
                                column_mapping, date_summary, digest, load_csv, csv_frames, file_digest,
                                missing, parse_dates, parse_numbers, project_path,
                                utc_now, write_json)

SUMMARY_LIMIT = 20


def json_label(value):
    return None if pd.isna(value) else str(value)


def values_summary(values: pd.Series) -> dict:
    known = sorted({str(value) for value in values.dropna()})
    return {"count": len(known), "values": known[:30], "values_truncated": len(known) > 30,
            "missing_rows": int(values.isna().sum())}


def clean_unit(values: pd.Series) -> pd.Series:
    result = values.mask(missing(values))
    return result.mask(result.astype(str).str.strip().str.casefold().isin(["unverified", "unknown"]))


def prepare_file(data: bytes | pd.DataFrame, meta: dict, date_format: str | None) -> tuple:
    raw = data if isinstance(data, pd.DataFrame) else load_csv(data, meta["encoding"], meta["delimiter"])
    mapping = column_mapping(list(raw.columns), meta["column_mapping"])
    # Reject header/mapping drift rather than make a different interpretation.
    if list(raw.columns) != meta["original_headers"] or len(raw) != meta["row_count"]:
        raise ValueError("Raw file shape differs from its provenance.")
    temporary = pd.DataFrame(index=raw.index)
    for field in CONFIG["aliases"]:
        temporary[field] = raw[mapping[field]] if field in mapping else ""
    for field in SERIES_FIELDS:
        temporary[field] = temporary[field].mask(missing(temporary[field]))
    selected_format = date_format if date_format is not None else meta.get("date_format")
    temporary["parsed_date"] = parse_dates(temporary["date"], selected_format)
    temporary["date_invalid"] = temporary["parsed_date"].isna()
    numeric_failures = {}
    for field in NUMERIC_FIELDS:
        temporary[f"parsed_{field}"] = parse_numbers(temporary[field])
        numeric_failures[field] = int((~missing(temporary[field]) & temporary[f"parsed_{field}"].isna()).sum())
    temporary["nonpositive_price"] = pd.concat(
        [temporary[f"parsed_{field}"].le(0) for field in PRICES], axis=1
    ).any(axis=1)
    complete = temporary[[f"parsed_{field}" for field in PRICES]].notna().all(axis=1)
    temporary["price_order_violation"] = complete & (
        temporary["parsed_min_price"].gt(temporary["parsed_modal_price"])
        | temporary["parsed_modal_price"].gt(temporary["parsed_max_price"])
    )
    temporary["price_incomplete"] = ~complete
    temporary["missing_identity"] = temporary[SERIES_FIELDS[:4]].isna().any(axis=1)
    for field in ["price_unit", "quantity_unit"]:
        observed = clean_unit(temporary[field])
        declared = meta.get(field, "unverified")
        declared_known = declared.strip().casefold() not in {"", "unknown", "unverified"}
        temporary[f"effective_{field}"] = observed.fillna(declared) if declared_known else observed
        temporary[f"{field}_declaration_conflict"] = (observed.notna() & observed.ne(declared)) if declared_known else False
    temporary["source_sha256"] = meta["sha256"]
    # Exact duplicate means equal original headers and string field values;
    # formatting in the immutable CSV bytes is still preserved separately.
    ordered_headers = sorted(raw.columns)
    temporary["raw_signature"] = [
        digest(json.dumps([ordered_headers, list(row)], ensure_ascii=False).encode("utf-8"))
        for row in raw[ordered_headers].itertuples(index=False, name=None)
    ]
    payload_fields = PRICES + ["arrivals", "effective_price_unit", "effective_quantity_unit", "unit"]
    temporary["payload_signature"] = [
        digest(json.dumps([json_label(value) for value in row], ensure_ascii=False).encode("utf-8"))
        for row in temporary[payload_fields].itertuples(index=False, name=None)
    ]
    info = {
        "sha256": meta["sha256"], "kind": meta["kind"], "rows": len(raw),
        "original_headers": list(raw.columns), "column_mapping": mapping,
        "unmapped_headers": [header for header in raw.columns if header not in mapping.values()],
        "missing_by_original_column": {column: int(missing(raw[column]).sum()) for column in raw.columns},
        "absent_canonical_fields": [field for field in CONFIG["aliases"] if field not in mapping],
        "dates": date_summary(temporary["date"], selected_format),
        "numeric_parse_failures": numeric_failures,
        "exact_duplicate_rows_beyond_first": int(raw.duplicated().sum()),
        "declared_price_unit": meta.get("price_unit", "unverified"),
        "declared_quantity_unit": meta.get("quantity_unit", "unverified"),
    }
    return temporary, info, raw.head(3).to_dict(orient="records")


def series_coverage(frame: pd.DataFrame) -> tuple[list[dict], dict]:
    identified = ~frame["missing_identity"] & frame["parsed_date"].notna()
    business = frame.loc[identified]
    key = SERIES_FIELDS + ["parsed_date"]
    groups = business.groupby(key, dropna=False, sort=False)
    sizes = groups.size()
    conflicts = groups["payload_signature"].nunique().gt(1)
    repeated = sizes.gt(1)
    frame["conflicting_key"] = False
    if len(business):
        flags = groups["payload_signature"].transform("nunique").gt(1)
        frame.loc[business.index, "conflicting_key"] = flags
    key_report = {
        "fields": key,
        "eligible_rows": int(identified.sum()),
        "excluded_missing_identity_or_date_rows": int((~identified).sum()),
        "repeated_keys": int(repeated.sum()),
        "rows_in_repeated_keys": int(sizes[repeated].sum()),
        "rows_beyond_first_per_key": int((sizes - 1).clip(lower=0).sum()),
        "conflicting_keys": int(conflicts.sum()),
        "rows_in_conflicting_keys": int(sizes[conflicts].sum()),
        "conflict_definition": "Same identity and parsed date but different original price/arrivals or unit payload; nothing is discarded",
    }
    series = []
    for labels, group in frame.loc[~frame["missing_identity"]].groupby(SERIES_FIELDS, dropna=False, sort=True):
        identifiers = dict(zip(SERIES_FIELDS, [json_label(label) for label in labels]))
        dates = sorted({value.date() for value in group["parsed_date"].dropna()})
        span = (dates[-1] - dates[0]).days + 1 if dates else 0
        gaps = []
        for before, after in zip(dates, dates[1:]):
            days = (after - before).days - 1
            if days:
                gaps.append({"after": before.isoformat(), "before": after.isoformat(), "missing_calendar_days": days})
        prices_ok = group["parsed_modal_price"].gt(0) & ~group["price_order_violation"]
        valid_target_days = int(group.loc[prices_ok, "parsed_date"].nunique())
        price_units = sorted({str(value) for value in group["effective_price_unit"].dropna()})
        quantity_units = sorted({str(value) for value in group["effective_quantity_unit"].dropna()})
        item = {
            "series": identifiers,
            "series_id": digest(json.dumps(identifiers, sort_keys=True).encode())[:16],
            "rows": len(group), "earliest": dates[0].isoformat() if dates else None,
            "latest": dates[-1].isoformat() if dates else None,
            "observation_days": len(dates), "positive_modal_observation_days": valid_target_days,
            "calendar_span_days": span,
            "calendar_coverage": round(len(dates) / span, 6) if span else None,
            "missing_calendar_days": span - len(dates),
            "gap_intervals_count": len(gaps),
            "longest_gap_days": max((gap["missing_calendar_days"] for gap in gaps), default=0),
            "first_gap_intervals": gaps[:10], "gap_intervals_truncated": len(gaps) > 10,
            "invalid_or_missing_date_rows": int(group["date_invalid"].sum()),
            "nonpositive_price_rows": int(group["nonpositive_price"].sum()),
            "price_order_violation_rows": int(group["price_order_violation"].sum()),
            "incomplete_or_unparseable_price_rows": int(group["price_incomplete"].sum()),
            "conflicting_key_rows": int(group["conflicting_key"].sum()),
            "price_units": price_units, "quantity_units": quantity_units,
            "missing_price_unit_rows": int(group["effective_price_unit"].isna().sum()),
            "missing_quantity_unit_with_arrivals_rows": int((~missing(group["arrivals"]) & group["effective_quantity_unit"].isna()).sum()),
            "unit_conflict": len(price_units) > 1 or len(quantity_units) > 1
                or bool(group["price_unit_declaration_conflict"].any())
                or bool(group["quantity_unit_declaration_conflict"].any()),
            "missing_variety_or_grade": identifiers["variety"] is None or identifiers["grade"] is None,
        }
        series.append(item)
    return series, key_report


def scope_recommendation(series: list[dict], kind: str, policy: dict | None = None,
                         allow_shorter: bool = True) -> dict:
    policy = dict(policy or CONFIG["scope_screening"])
    reasons = {}
    eligible = []
    for item in series:
        rejected = []
        if policy.get("required_state") and item["series"]["state"] != policy["required_state"]:
            rejected.append("outside user-selected project state")
        if item["calendar_span_days"] < policy["minimum_span_days"]:
            rejected.append("history shorter than screening span")
        if item["positive_modal_observation_days"] < policy["minimum_observation_days"]:
            rejected.append("too few positive modal observation days")
        if (item["calendar_coverage"] or 0) < policy["minimum_calendar_coverage"]:
            rejected.append("calendar coverage below screening threshold")
        if item["longest_gap_days"] > policy["maximum_internal_gap_days"]:
            rejected.append("long internal calendar gap requires review")
        if item["missing_variety_or_grade"]:
            rejected.append("variety or grade unknown")
        if item["missing_price_unit_rows"] or len(item["price_units"]) != 1 or item["unit_conflict"]:
            rejected.append("units missing or conflicting")
        if any(item[field] for field in ["invalid_or_missing_date_rows", "nonpositive_price_rows",
                                        "price_order_violation_rows", "incomplete_or_unparseable_price_rows",
                                        "conflicting_key_rows"]):
            rejected.append("unresolved data quality flags")
        for reason in rejected:
            reasons[reason] = reasons.get(reason, 0) + 1
        if not rejected:
            eligible.append(item)
    result = {"status": "pending", "policy": policy, "eligible_series_count": len(eligible),
              "rejection_reason_counts": reasons, "state": None, "commodities": [],
              "selected_series": [], "state_candidates": [],
              "note": "Need observed historical coverage before choosing a state, three commodities, and 10-20 combinations."}
    if kind != "historical":
        result["note"] = "Snapshot inputs are excluded from historical scope recommendations regardless of row count."
        return result
    # One representative variety/grade per combination; never average unlike
    # series. Units must match across the chosen scope (no conversions today).
    candidates = []
    buckets = {}
    for item in eligible:
        buckets.setdefault((item["series"]["state"], item["price_units"][0]), []).append(item)
    for (state, price_unit), items in buckets.items():
        best = {}
        for item in sorted(items, key=lambda s: (-s["positive_modal_observation_days"], -s["calendar_span_days"], s["longest_gap_days"], s["series_id"])):
            identity = item["series"]
            combo = tuple(identity[field] for field in SERIES_FIELDS[:4])
            best.setdefault(combo, item)
        by_commodity = {}
        for item in best.values():
            by_commodity.setdefault(item["series"]["commodity"], []).append(item)
        ranked = sorted(by_commodity, key=lambda c: (-len(by_commodity[c]),
                        -sum(s["positive_modal_observation_days"] for s in by_commodity[c]), c))
        chosen_commodities = ranked[:policy["desired_commodities"]]
        selected = []
        # Round-robin makes all chosen commodities represented within the cap.
        for index in range(policy["max_combinations"]):
            for commodity in chosen_commodities:
                if index < len(by_commodity[commodity]) and len(selected) < policy["max_combinations"]:
                    selected.append(by_commodity[commodity][index])
        candidate = {"state": state, "price_unit": price_unit,
                     "commodities": chosen_commodities,
                     "available_combinations": len(best), "selected_series": selected,
                     "supports_desired_scope": len(chosen_commodities) == policy["desired_commodities"]
                        and len(selected) >= policy["min_combinations"]}
        candidates.append(candidate)
    # The user's required state takes precedence over geographic preferences.
    candidates.sort(key=lambda c: (not c["supports_desired_scope"],
                                  c["state"].casefold() != policy["preferred_state"].casefold(),
                                  -len(c["selected_series"]), c["state"], c["price_unit"]))
    result["state_candidates"] = [{key: value for key, value in candidate.items() if key != "selected_series"}
                                  for candidate in candidates[:SUMMARY_LIMIT]]
    result["state_candidates_truncated"] = len(candidates) > SUMMARY_LIMIT
    if candidates:
        chosen = candidates[0]
        result.update({"state": chosen["state"], "commodities": chosen["commodities"],
                       "selected_series": chosen["selected_series"], "price_unit": chosen["price_unit"],
                       "status": "provisional_recommendation" if chosen["supports_desired_scope"] else "insufficient_scope",
                       "note": "Selection respects the user-selected project state. Each combination retains one explicitly listed variety/grade; no merging. Thresholds are project screening choices, not evidence of predictive accuracy."})
    elif allow_shorter and kind == "historical" and policy.get("shorter_history_minimum_span_days"):
        shorter = scope_recommendation(series, kind,
                    {**policy, "minimum_span_days": policy["shorter_history_minimum_span_days"]}, False)
        if shorter["selected_series"]:
            shorter["strict_target_status"] = result["status"]
            shorter["strict_target_eligible_series_count"] = len(eligible)
            shorter["strict_target_minimum_span_days"] = policy["minimum_span_days"]
            shorter["strict_target_rejection_reason_counts"] = reasons
            shorter["status"] = "provisional_shorter_history" if shorter["status"] == "provisional_recommendation" else "insufficient_shorter_history_scope"
            shorter["note"] = (f"No series meets the original {policy['minimum_span_days']}-day screen. "
                f"This explicitly shorter-history option uses {policy['shorter_history_minimum_span_days']} days minimum; "
                "it does not fulfill the two-year target. Keep each listed variety/grade separate; do not join FAQ and Non-FAQ. "
                "The project state remains Gujarat. All other quality, unit, observation-count and gap screens still apply.")
            return shorter
    return result


def profile_bundles(raw_root: Path, kind: str = "historical", date_format: str | None = None,
                    state: str | None = None, commodities: list[str] | None = None) -> tuple:
    manifests = sorted((raw_root / kind).glob("*/provenance.json"))
    frames, files, samples = [], [], []
    seen = set()
    source_files = []
    state_rows, state_missing_dates, state_failed_dates = 0, 0, 0
    state_dates, commodity_audit, state_counts = set(), {}, {}
    for manifest in manifests:
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        source_path = manifest.parent / "source.csv"
        if file_digest(source_path) != meta["sha256"] or manifest.parent.name != meta["sha256"]:
            raise ValueError("An imported file failed its SHA-256 provenance check; restore the original before profiling.")
        if meta["kind"] != kind or meta["sha256"] in seen:
            raise ValueError("Bundle kind/identity conflict found. Inspect raw bundles before profiling.")
        seen.add(meta["sha256"])
        selected, scanned_rows = [], 0
        mapping = meta["column_mapping"]
        for chunk in csv_frames(source_path, meta["encoding"], meta["delimiter"]):
            if list(chunk.columns) != meta["original_headers"]:
                raise ValueError("Raw headers differ from provenance.")
            scanned_rows += len(chunk)
            if "state" in mapping:
                for label, count in chunk[mapping["state"]].value_counts().items():
                    state_counts[label] = state_counts.get(label, 0) + int(count)
            if state and "state" not in mapping:
                raise ValueError("Cannot apply a state filter: source lacks a mapped state column.")
            subset = chunk.loc[chunk[mapping["state"]].eq(state)] if state else chunk
            state_rows += len(subset)
            parsed = parse_dates(subset[mapping["date"]], date_format or meta.get("date_format")) if "date" in mapping else pd.Series(pd.NaT, index=subset.index)
            state_dates.update(value.date().isoformat() for value in parsed.dropna().unique())
            if "date" in mapping:
                state_missing_dates += int(missing(subset[mapping["date"]]).sum())
                state_failed_dates += int((~missing(subset[mapping["date"]]) & parsed.isna()).sum())
            if "commodity" in mapping:
                for name, rows in subset.groupby(mapping["commodity"], sort=False):
                    item = commodity_audit.setdefault(name, {"rows": 0, "dates": set(), "markets": set()})
                    item["rows"] += len(rows)
                    item["dates"].update(value.date().isoformat() for value in parsed.loc[rows.index].dropna().unique())
                    if "market" in mapping and "district" in mapping:
                        item["markets"].update(zip(rows[mapping["district"]], rows[mapping["market"]]))
            if commodities:
                if "commodity" not in mapping:
                    raise ValueError("Cannot apply commodity filter: source lacks a mapped commodity column.")
                subset = subset.loc[subset[mapping["commodity"]].isin(commodities)]
            if len(subset):
                selected.append(subset)
        if scanned_rows != meta["row_count"]:
            raise ValueError("Raw row count differs from provenance.")
        source_files.append({key: meta.get(key) for key in ["original_filename", "sha256", "row_count", "bytes", "original_headers", "observed_date_range", "source_url", "publisher", "license_attribution_status", "price_unit", "quantity_unit"]})
        raw = pd.concat(selected, ignore_index=True) if selected else pd.DataFrame(columns=meta["original_headers"], dtype=str)
        frame, info, sample = prepare_file(raw, {**meta, "row_count": len(raw)}, date_format)
        frames.append(frame)
        files.append(info)
        samples.append({"sha256": meta["sha256"], "original_headers": meta["original_headers"], "sample": sample})
    result = {
        "schema_version": 1, "generated_at_utc": utc_now(), "kind": kind,
        "status": "acquisition_pending" if not frames else "profiled",
        "imported_file_count": len(files), "row_count": sum(len(frame) for frame in frames),
        "input_files": source_files,
        "input_row_count": sum(item["row_count"] for item in source_files),
        "source_state_counts": state_counts,
        "filters": {"state": state, "commodities": commodities},
        "statistics_scope": "Quality/duplicates/series counts apply only to filtered rows; input inventory and state audit are separately labeled.",
        "state_audit": {"state": state, "rows": state_rows,
                        "earliest": min(state_dates) if state_dates else None,
                        "latest": max(state_dates) if state_dates else None,
                        "distinct_observation_dates": len(state_dates),
                        "missing_dates": state_missing_dates, "date_parse_failures": state_failed_dates,
                        "commodities": {name: {"rows": item["rows"], "earliest": min(item["dates"]) if item["dates"] else None,
                                              "latest": max(item["dates"]) if item["dates"] else None,
                                              "observation_days": len(item["dates"]), "district_market_combinations": len(item["markets"])}
                                        for name, item in sorted(commodity_audit.items())}},
        "files": files[:SUMMARY_LIMIT], "files_truncated": len(files) > SUMMARY_LIMIT,
        "all_file_profiles_local": "local/file_profiles.json",
        "sample_local_only": "local/samples.json",
        "coverage_local_only": "local/series_coverage.csv",
        "definitions": {
            "missing": CONFIG["missing_tokens"],
            "date_policy": "Explicit import date format or profile override; otherwise strict ISO YYYY-MM-DD only. No day/month guessing.",
            "missing_variety_grade": "Separate unknown buckets (null), never merged with known values; excluded from automatic scope selection.",
            "missing_identity": "Rows lacking state, district, market, or commodity are counted but excluded from keys and series coverage.",
            "coverage": "Unique parsed dates divided by inclusive first-to-last calendar span, per state/district/market/commodity/variety/grade.",
            "gaps": "Internal calendar gaps only; no zero fill, no inferred leading/trailing gaps. Closures/non-reporting are possible.",
            "numbers": "Temporary parsing only. Nonfinite values fail; currency signs and comma thousands separators are not guessed.",
            "units": "Explicit per-row units or user-confirmed provenance declaration; generic Unit is reported separately and never assigned automatically.",
        },
        "next_import_command": '.\\.venv\\Scripts\\python.exe scripts\\import_market_data.py "C:\\path\\to\\official-history.csv" --source enam_agmarknet --kind historical --date-format "%d/%m/%Y"',
    }
    if not frames or not result["row_count"]:
        if frames:
            result["status"] = "no_observations"
        result.update({"dates": None, "series_count": 0, "series_preview": [],
                       "scope_recommendation": scope_recommendation([], kind)})
        return result, [], samples, files
    frame = pd.concat(frames, ignore_index=True)
    series, key_report = series_coverage(frame)
    valid_dates = frame["parsed_date"].dropna()
    result.update({
        "dates": {"earliest": valid_dates.min().date().isoformat() if len(valid_dates) else None,
                  "latest": valid_dates.max().date().isoformat() if len(valid_dates) else None,
                  "distinct_observation_dates": int(valid_dates.nunique()),
                  "missing_rows": int(missing(frame["date"]).sum()),
                  "parse_failures": int((~missing(frame["date"]) & frame["parsed_date"].isna()).sum())},
        "dimensions": {field: values_summary(frame[field]) for field in SERIES_FIELDS},
        "missing_by_canonical_field": {field: int(frame[field].isna().sum()) if field in SERIES_FIELDS else int(missing(frame[field]).sum()) for field in CONFIG["aliases"]},
        "numeric_parse_failures": {field: sum(file["numeric_parse_failures"][field] for file in files) for field in NUMERIC_FIELDS},
        "exact_duplicate_rows_beyond_first": int(frame["raw_signature"].duplicated().sum()),
        "candidate_business_keys": key_report,
        "nonpositive_prices": {field: int(frame[f"parsed_{field}"].le(0).sum()) for field in PRICES},
        "price_order_violation_rows": int(frame["price_order_violation"].sum()),
        "price_order_uncheckable_rows": int(frame["price_incomplete"].sum()),
        "rows_missing_series_identity": int(frame["missing_identity"].sum()),
        "units": {"price": values_summary(frame["effective_price_unit"]),
                  "quantity": values_summary(frame["effective_quantity_unit"]),
                  "generic_unassigned_unit": values_summary(frame["unit"].mask(missing(frame["unit"]))),
                  "price_declaration_conflict_rows": int(frame["price_unit_declaration_conflict"].sum()),
                  "quantity_declaration_conflict_rows": int(frame["quantity_unit_declaration_conflict"].sum()),
                  "series_with_conflicting_units": sum(s["unit_conflict"] for s in series)},
        "series_count": len(series), "series_preview": series[:SUMMARY_LIMIT],
        "series_preview_truncated": len(series) > SUMMARY_LIMIT,
        "scope_recommendation": scope_recommendation(series, kind),
        "commodity_grade_coverage": [
            {"commodity": json_label(labels[0]), "grade": json_label(labels[1]), "rows": len(group),
             "earliest": group["parsed_date"].min().date().isoformat() if group["parsed_date"].notna().any() else None,
             "latest": group["parsed_date"].max().date().isoformat() if group["parsed_date"].notna().any() else None,
             "observation_days": int(group["parsed_date"].nunique())}
            for labels, group in frame.groupby(["commodity", "grade"], dropna=False, sort=True)
        ],
    })
    return result, series, samples, files


def markdown(result: dict) -> str:
    lines = ["# AgriSense data profile", "", f"Status: **{result['status']}**",
             f"Input kind: **{result['kind']}**", f"Generated UTC: {result['generated_at_utc']}", "",
             "Project owner: Krishkumar | Roll No: 2401CS83 | IIT Patna",
             "Repository: https://github.com/Krish290107/agrisense", ""]
    if result["status"] in {"acquisition_pending", "no_observations"}:
        lines += ["No real observations are available in the selected imported bundles. Historical date coverage and an evidence-based state/commodity recommendation remain pending.",
                  "", "Next command (replace the path and confirm the export's date format):", "", "```powershell", result["next_import_command"], "```", ""]
    else:
        dates = result["dates"]
        audit = result["state_audit"]
        lines += ["## Input inventory and project filter", "",
                  f"All-state input rows: {result['input_row_count']:,}. Selected project rows: {result['row_count']:,}.",
                  f"State filter: {result['filters']['state']}; commodity filter: {', '.join(result['filters']['commodities'] or ['all'])}.",
                  f"State-wide audit before commodity filtering: {audit['rows']:,} rows, {audit['earliest']} to {audit['latest']}, {audit['distinct_observation_dates']} distinct dates.",
                  "", "| File | All-state rows | Actual first date | Actual last date | Distinct dates |", "| --- | ---: | --- | --- | ---: |"]
        for item in result["input_files"]:
            coverage = item["observed_date_range"] or {}
            lines.append(f"| {item['original_filename']} | {item['row_count']:,} | {coverage.get('earliest')} | {coverage.get('latest')} | {coverage.get('distinct_observation_dates')} |")
        lines += ["", "| Commodity in selected state | Rows | First date | Last date | Observation dates | Markets (district + market) |",
                  "| --- | ---: | --- | --- | ---: | ---: |"]
        for commodity in result["filters"]["commodities"] or []:
            item = audit["commodities"].get(commodity)
            if item:
                lines.append(f"| {commodity} | {item['rows']:,} | {item['earliest']} | {item['latest']} | {item['observation_days']} | {item['district_market_combinations']} |")
        lines += ["", "## Quality of filtered project records", ""]
        lines += [f"Files: {result['imported_file_count']}; rows: {result['row_count']}; series: {result['series_count']}.",
                  f"Actual parsed date range: {dates['earliest']} to {dates['latest']} ({dates['distinct_observation_dates']} distinct dates).", "",
                  "| Check | Count |", "| --- | ---: |",
                  f"| Missing dates | {dates['missing_rows']} |",
                  f"| Date parse failures | {dates['parse_failures']} |",
                  f"| Exact duplicate rows beyond first | {result['exact_duplicate_rows_beyond_first']} |",
                  f"| Repeated candidate keys | {result['candidate_business_keys']['repeated_keys']} |",
                  f"| Conflicting candidate keys | {result['candidate_business_keys']['conflicting_keys']} |",
                  f"| Price order violations | {result['price_order_violation_rows']} |",
                  f"| Price order uncheckable rows | {result['price_order_uncheckable_rows']} |", "",
                  f"Nonpositive prices by column: {result['nonpositive_prices']}.",
                  f"Numeric parsing failures: {result['numeric_parse_failures']}.",
                  f"Price units: {', '.join(result['units']['price']['values']) or 'unverified'}; missing price-unit rows: {result['units']['price']['missing_rows']}. Source declarations are recorded in input provenance; absent quantity fields are not invented.",
                  "",
                  "See data_profile.json for per-column missingness, numeric failures, nonpositive prices, dimensions, units, and compact series coverage.", ""]
        lines += ["## Grade coverage (pooled dates, not joined series)", "",
                  "| Commodity | Grade | Rows | First | Last | Distinct dates |",
                  "| --- | --- | ---: | --- | --- | ---: |"]
        for item in result["commodity_grade_coverage"]:
            lines.append(f"| {item['commodity']} | {item['grade']} | {item['rows']} | {item['earliest']} | {item['latest']} | {item['observation_days']} |")
        lines += ["", "These grade totals pool several markets/varieties for inspection only. They are not a forecasting series.", "", "## Scope recommendation", ""]
        recommendation = result["scope_recommendation"]
        lines += [f"Scope status: **{recommendation['status']}**.", recommendation["note"], ""]
        if recommendation["state"]:
            lines += [f"Candidate state: {recommendation['state']}.",
                      "Candidate commodities: " + ", ".join(recommendation["commodities"]) + ".",
                      f"Selected combinations: {len(recommendation['selected_series'])}; their exact varieties, grades, counts, gaps and units appear in the JSON recommendation.", ""]
            lines += ["| District | Market | Commodity | Variety | Grade | First | Last | Days observed | Coverage | Longest gap |",
                      "| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |"]
            for item in recommendation["selected_series"]:
                identity = item["series"]
                lines.append("| " + " | ".join(str(identity[f]).replace("|", "\\|") for f in ["district", "market", "commodity", "variety", "grade"])
                             + f" | {item['earliest']} | {item['latest']} | {item['observation_days']} | {item['calendar_coverage']:.1%} | {item['longest_gap_days']} |")
            lines += ["", "Full two-year, same-series coverage remains unmet. Any shorter-history recommendation is provisional for later cleaning and validation, not permission to merge grades or fill missing prices.", ""]
    lines += ["## Read alongside this report", "",
              "- `data_profile.json`: small aggregate report; previews are capped at 20 files/series.",
              "- `local/series_coverage.csv`: every identifiable series, its observation days, span, gaps and quality flags (ignored by Git).",
              "- `local/file_profiles.json`: every file's columns, mappings and quality counts (ignored by Git).",
              "- `local/samples.json`: at most three original rows per file, for local inspection only (ignored by Git).",
              "", "Missing variety/grade stays unknown. Incomplete state/district/market/commodity rows are reported separately. Missing dates are never zero prices; gaps may reflect closures or non-reporting.",
              "", "These tools inspect data; they do not clean, impute, deduplicate, merge varieties, train, or establish forecasting accuracy.", ""]
    return "\n".join(lines)


def write_reports(result: dict, series: list, samples: list, files: list, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "data_profile.json", result)
    (output / "DATA_PROFILE.md").write_text(markdown(result), encoding="utf-8")
    write_json(output / "local/samples.json", {"warning": "LOCAL OBSERVATIONS; do not commit or use as a training table", "files": samples})
    write_json(output / "local/file_profiles.json", {"files": files})
    rows = []
    for item in series:
        rows.append({**item["series"], **{key: json.dumps(value) if isinstance(value, (list, dict)) else value
                     for key, value in item.items() if key != "series"}})
    pd.DataFrame(rows, columns=None if rows else SERIES_FIELDS + ["observation_days", "calendar_span_days", "missing_calendar_days"]).to_csv(output / "local/series_coverage.csv", index=False)
    selected = []
    for item in result["scope_recommendation"]["selected_series"]:
        selected.append({**item["series"], "series_id": item["series_id"],
                         **{key: item[key] for key in ["rows", "earliest", "latest", "observation_days", "calendar_span_days", "calendar_coverage", "missing_calendar_days", "longest_gap_days"]},
                         "price_unit": item["price_units"][0], "recommendation_status": result["scope_recommendation"]["status"]})
    pd.DataFrame(selected, columns=None if selected else SERIES_FIELDS + ["series_id", "observation_days"]).to_csv(output / "recommended_scope.csv", index=False)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=["historical", "snapshots"], default="historical")
    parser.add_argument("--state", default=CONFIG["scope_screening"].get("required_state"))
    parser.add_argument("--commodities", nargs="+", default=CONFIG["scope_screening"]["candidate_commodities"])
    parser.add_argument("--all-records", action="store_true", help="Explicitly disable filters; selected records are held in memory")
    parser.add_argument("--date-format", help="Explicit override for all selected files; otherwise use each import's format")
    parser.add_argument("--output-dir", help="Repository-relative or absolute report directory; defaults to reports/data (snapshot reports go under reports/data/local/snapshots)")
    args = parser.parse_args()
    try:
        output = project_path(args.output_dir) if args.output_dir else ROOT / ("reports/data" if args.kind == "historical" else "reports/data/local/snapshots")
        if output.is_relative_to((ROOT / "data").resolve()):
            raise ValueError("Reports must be outside data/ so source observations cannot be overwritten.")
        result, series, samples, files = profile_bundles(ROOT / "data/raw", args.kind, args.date_format,
                                                       None if args.all_records else args.state,
                                                       None if args.all_records else args.commodities)
        write_reports(result, series, samples, files, output)
        print(f"Profile status: {result['status']}; kind: {args.kind}; files: {result['imported_file_count']}; rows: {result['row_count']}.")
        print(f"Reports: {output / 'DATA_PROFILE.md'}")
        return 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # No source observations, URLs, or credentials in failure messages.
        message = str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else "Check bundle files, provenance format and output permissions."
        print(f"Profile error: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
