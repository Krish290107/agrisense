"""Shared local data utilities. Original CSV bytes are never rewritten."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "configs/data_sources.json").read_text(encoding="utf-8"))
SERIES_FIELDS = ["state", "district", "market", "commodity", "variety", "grade"]
PRICES = ["min_price", "modal_price", "max_price"]
NUMERIC_FIELDS = PRICES + ["arrivals"]
SAFE_PARAMETERS = {"state", "district", "market", "commodity", "variety", "grade",
                   "from_date", "to_date", "date", "offset", "limit", "format"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def project_path(value: str | Path) -> Path:
    path = Path(value).expanduser()
    return (path if path.is_absolute() else ROOT / path).resolve()


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            checksum.update(block)
    return checksum.hexdigest()


def csv_frames(path: Path, encoding="utf-8-sig", delimiter=",", chunk_size=100_000):
    """Bounded-memory CSV reading with the same strict, string-only semantics."""
    if len(delimiter) != 1:
        raise ValueError("Delimiter must be exactly one character.")
    with path.open(encoding=encoding, newline="") as stream:
        reader = csv.reader(stream, delimiter=delimiter, strict=True)
        headers = next(reader, None)
        if not headers or any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
            raise ValueError("CSV headers must be nonempty and unique.")
        batch = []
        yielded = False
        for index, row in enumerate(reader, start=2):
            row = row or [""] * len(headers)
            if len(row) != len(headers):
                raise ValueError(f"CSV record {index} has {len(row)} fields; expected {len(headers)}.")
            batch.append(row)
            if len(batch) >= chunk_size:
                yield pd.DataFrame(batch, columns=headers, dtype=str)
                yielded = True
                batch = []
        if batch or not yielded:
            yield pd.DataFrame(batch, columns=headers, dtype=str)


def safe_url(value: str | None) -> str | None:
    """Remove credentials/fragments and all query values (even unknown key names)."""
    if not value:
        return None
    parts = urlsplit(value)
    if parts.scheme not in {"https", "http"} or not parts.hostname:
        raise ValueError("Source URL must be a complete HTTP(S) URL.")
    host = parts.hostname
    if ":" in host:
        host = f"[{host}]"
    if parts.port:
        host += f":{parts.port}"
    query = urlencode([(key, "[REDACTED]") for key, _ in parse_qsl(parts.query)])
    return urlunsplit((parts.scheme, host, parts.path, query, ""))


def safe_parameters(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        key, sep, item = value.partition("=")
        if not sep or not key.strip():
            raise ValueError("Each retrieval parameter must have the form name=value.")
        key = key.strip()
        result[key] = item if key.casefold() in SAFE_PARAMETERS else "[REDACTED]"
    return result


def missing(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.casefold().isin(CONFIG["missing_tokens"])


def load_csv(data: bytes, encoding: str = "utf-8-sig", delimiter: str = ",") -> pd.DataFrame:
    if len(delimiter) != 1:
        raise ValueError("Delimiter must be exactly one character.")
    # Preserve NA markers/leading zeroes and reject bad widths without pandas inference.
    try:
        rows = list(csv.reader(io.StringIO(data.decode(encoding), newline=""),
                               delimiter=delimiter, strict=True))
    except (UnicodeError, csv.Error, LookupError) as exc:
        raise ValueError("CSV decoding/parsing failed; verify --encoding and --delimiter.") from exc
    if not rows or not rows[0]:
        raise ValueError("CSV has no header row.")
    headers = rows[0]
    if any(not h.strip() for h in headers) or len(set(headers)) != len(headers):
        raise ValueError("CSV headers must be nonempty and unique; preserve the original and obtain an unambiguous export.")
    values = []
    for index, row in enumerate(rows[1:], start=2):
        row = row if row else [""] * len(headers)
        if len(row) != len(headers):
            raise ValueError(f"CSV record {index} has {len(row)} fields; expected {len(headers)}. Nothing was imported.")
        values.append(row)
    return pd.DataFrame(values, columns=headers, dtype=str)


def column_mapping(headers: list[str], override: dict | None = None) -> dict[str, str]:
    normalize = lambda value: re.sub(r"[^a-z0-9]", "", value.casefold())
    override = override or {}
    if not isinstance(override, dict) or any(not isinstance(value, str) for value in override.values()):
        raise ValueError("Column map must be a JSON object mapping canonical fields to original header strings.")
    if set(override) - set(CONFIG["aliases"]):
        raise ValueError("Column map contains an unknown canonical field.")
    mapping = {}
    for canonical, aliases in CONFIG["aliases"].items():
        if canonical in override:
            if override[canonical] not in headers:
                raise ValueError(f"Mapped column for {canonical} does not exist.")
            mapping[canonical] = override[canonical]
            continue
        names = {normalize(alias) for alias in aliases}
        matches = [header for header in headers if normalize(header) in names]
        if len(matches) > 1:
            raise ValueError(f"Multiple columns match {canonical}; provide --column-map with an explicit selection.")
        if matches:
            mapping[canonical] = matches[0]
    if len(set(mapping.values())) != len(mapping):
        raise ValueError("A source column cannot map to multiple canonical fields.")
    return mapping


def parse_dates(values: pd.Series, date_format: str | None) -> pd.Series:
    if date_format and ("%Y" not in date_format or "%d" not in date_format
                        or not any(token in date_format for token in ("%m", "%b", "%B"))):
        raise ValueError("Date format must explicitly include four-digit year, month, and day (for example %d/%m/%Y).")
    text = values.astype(str).str.strip().mask(missing(values))
    if date_format is None:
        # Only ISO date syntax is accepted automatically. 01/02/2025 is never guessed.
        text = text.where(text.str.fullmatch(r"\d{4}-\d{2}-\d{2}", na=False))
    return pd.to_datetime(text, format=date_format or "%Y-%m-%d", errors="coerce", exact=True)


def date_summary(values: pd.Series, date_format: str | None) -> dict:
    parsed = parse_dates(values, date_format)
    valid = parsed.dropna()
    return {
        "earliest": valid.min().date().isoformat() if len(valid) else None,
        "latest": valid.max().date().isoformat() if len(valid) else None,
        "distinct_observation_dates": int(valid.nunique()),
        "missing": int(missing(values).sum()),
        "parse_failures": int((~missing(values) & parsed.isna()).sum()),
        "date_format": date_format or "ISO-only: %Y-%m-%d",
    }


def parse_numbers(values: pd.Series) -> pd.Series:
    # No currency stripping, thousands-separator guessing, or unit conversion.
    numeric = pd.to_numeric(values.astype(str).str.strip().mask(missing(values)), errors="coerce")
    return numeric.where(numeric.map(lambda value: pd.isna(value) or math.isfinite(float(value))))


def write_json(path: Path, value: dict, *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x" if exclusive else "w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
        stream.write("\n")
