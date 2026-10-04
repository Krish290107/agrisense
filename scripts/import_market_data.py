"""Import real CSVs byte-for-byte with immutable SHA-256 provenance bundles."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

from market_data_common import (CONFIG, ROOT, column_mapping, date_summary, file_digest, csv_frames, parse_dates,
                                project_path, safe_parameters, safe_url,
                                utc_now, write_json)


def import_file(path: Path, *, raw_root: Path, source: dict, kind: str,
                date_format: str | None, encoding: str = "utf-8-sig", delimiter: str = ",",
                mapping_override: dict | None = None, acquired_at: str | None = None,
                retrieval_parameters: dict | None = None) -> dict:
    checksum = file_digest(path)
    raw_root = raw_root.resolve()
    for existing_kind in ("historical", "snapshots"):
        existing = raw_root / existing_kind / checksum
        if existing.exists():
            if not (existing / "provenance.json").is_file() or not (existing / "source.csv").is_file():
                raise ValueError("An incomplete import bundle exists; inspect it before retrying.")
            if file_digest(existing / "source.csv") != checksum:
                raise ValueError("Existing raw bundle failed its checksum; no files were overwritten.")
            if existing_kind != kind:
                raise ValueError("Identical content is already imported under another kind; it cannot be silently relabeled.")
            return {"status": "duplicate_skipped", "sha256": checksum,
                    "bundle": str(existing), "note": "Existing provenance retained; no files overwritten."}
    row_count, observed, date_missing, date_failures = 0, set(), 0, 0
    for frame in csv_frames(path, encoding, delimiter):
        headers = list(frame.columns)
        mapping = column_mapping(headers, mapping_override)
        row_count += len(frame)
        if "date" in mapping:
            summary = date_summary(frame[mapping["date"]], date_format)
            date_missing += summary["missing"]
            date_failures += summary["parse_failures"]
            observed.update(value.date().isoformat() for value in parse_dates(frame[mapping["date"]], date_format).dropna().unique())
    dates = {"earliest": min(observed) if observed else None,
             "latest": max(observed) if observed else None,
             "distinct_observation_dates": len(observed), "missing": date_missing,
             "parse_failures": date_failures, "date_format": date_format or "ISO-only: %Y-%m-%d"} if "date" in mapping else None
    metadata = {
        "schema_version": 1,
        "kind": kind,
        "source_url": safe_url(source.get("url")),
        "publisher": source.get("publisher") or "unverified",
        "original_filename": path.name,
        "imported_at_utc": utc_now(),
        "acquired_at_utc": acquired_at,
        "sha256": checksum,
        "bytes": path.stat().st_size,
        "row_count": row_count,
        "original_headers": headers,
        "column_mapping": mapping,
        "encoding": encoding,
        "delimiter": delimiter,
        "date_format": date_format,
        "observed_date_range": dates,
        "price_unit": source.get("price_unit") or "unverified",
        "quantity_unit": source.get("quantity_unit") or "unverified",
        "license_attribution_status": source.get("license_status") or "unverified",
        "retrieval_parameters": retrieval_parameters or {},
        "interpretation": "kind describes declared acquisition intent; actual historical adequacy is determined by profiling",
    }
    destination = raw_root / kind / checksum
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Stage the complete bundle inside its known destination parent. Rename makes
    # the two files visible together; TemporaryDirectory owns only this new folder.
    with tempfile.TemporaryDirectory(prefix=".import-", dir=destination.parent) as staging:
        staged_bundle = Path(staging) / "bundle"
        staged_bundle.mkdir()
        shutil.copyfile(path, staged_bundle / "source.csv")
        if file_digest(staged_bundle / "source.csv") != checksum:
            raise ValueError("Source changed during import; no bundle was published. Retry with a stable file.")
        write_json(staged_bundle / "provenance.json", metadata, exclusive=True)
        if destination.exists():
            raise ValueError("Another import created this bundle. Rerun to check the duplicate safely.")
        os.rename(staged_bundle, destination)
    return {"status": "imported", "sha256": checksum, "rows": row_count,
            "bundle": str(destination), "dates": dates}


def collect_inputs(path: Path, raw_root: Path) -> list[Path]:
    managed = [raw_root / name for name in ("historical", "snapshots")]
    def is_managed(candidate):
        return any(candidate.resolve().is_relative_to(folder.resolve()) for folder in managed)
    if is_managed(path):
        raise ValueError("Choose an original CSV, not a managed historical/snapshot bundle.")
    files = sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.casefold() == ".csv" and not is_managed(p)) if path.is_dir() else [path]
    if not files or any(not p.is_file() or p.suffix.casefold() != ".csv" for p in files):
        raise ValueError("Input must contain at least one existing CSV file.")
    return files


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("input", help="One CSV or directory; relative paths resolve from the repository root")
    result.add_argument("--source", choices=CONFIG["sources"], help="Known publisher/source metadata")
    result.add_argument("--source-url", help="Public source page URL; query values are redacted")
    result.add_argument("--publisher")
    result.add_argument("--kind", choices=["historical", "snapshots"], required=True)
    result.add_argument("--date-format", help="Explicit strptime date format, e.g. %%d/%%m/%%Y; otherwise ISO dates only")
    result.add_argument("--encoding", default="utf-8-sig")
    result.add_argument("--delimiter", default=",")
    result.add_argument("--column-map", help="JSON file of canonical field to original header overrides")
    result.add_argument("--price-unit", help="Confirmed price denomination, e.g. INR/quintal; never inferred")
    result.add_argument("--quantity-unit", help="Confirmed arrivals unit, e.g. tonne; never inferred")
    result.add_argument("--license-status", help="Confirmed terms/attribution, or unverified")
    result.add_argument("--acquired-at", help="Known acquisition timestamp, ISO 8601 UTC ending Z; otherwise unknown")
    result.add_argument("--parameter", action="append", default=[], help="Retrieval name=value; only documented non-secret fields are retained")
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        path = project_path(args.input)
        raw_root = ROOT / "data/raw"
        files = collect_inputs(path, raw_root)
        source = dict(CONFIG["sources"].get(args.source, {}))
        for field, value in (("url", args.source_url), ("publisher", args.publisher),
                             ("price_unit", args.price_unit), ("quantity_unit", args.quantity_unit),
                             ("license_status", args.license_status)):
            if value is not None:
                source[field] = value
        if args.source == "data_gov_in" and args.kind != "snapshots":
            raise ValueError("The verified data.gov.in catalog describes a current snapshot. Use --kind snapshots.")
        if args.acquired_at:
            from datetime import datetime
            if not args.acquired_at.endswith("Z"):
                raise ValueError("--acquired-at must be a UTC ISO timestamp ending in Z.")
            datetime.fromisoformat(args.acquired_at.replace("Z", "+00:00"))
        override = json.loads(project_path(args.column_map).read_text(encoding="utf-8")) if args.column_map else None
        parameters = safe_parameters(args.parameter)
        failed = 0
        for file in files:
            try:
                result = import_file(file, raw_root=raw_root, source=source, kind=args.kind,
                                     date_format=args.date_format, encoding=args.encoding,
                                     delimiter=args.delimiter, mapping_override=override,
                                     acquired_at=args.acquired_at, retrieval_parameters=parameters)
                print(json.dumps(result, ensure_ascii=True))
            except (ValueError, OSError) as exc:
                failed += 1
                # Do not print input paths, CLI metadata, URLs, or exception bodies
                # which might contain credentials supplied by a caller.
                print(f"Import failed for CSV {files.index(file) + 1}: {type(exc).__name__}. {str(exc) if isinstance(exc, ValueError) else 'Check file access and permissions.'}", file=sys.stderr)
        return 1 if failed else 0
    except (ValueError, OSError, TypeError) as exc:
        print(f"Import error: {str(exc) if isinstance(exc, ValueError) and not isinstance(exc, json.JSONDecodeError) else 'Check input/configuration paths and JSON format.'}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
