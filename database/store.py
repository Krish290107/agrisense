"""SQLite repository; decimal price strings preserve source precision exactly."""

from contextlib import contextmanager
import csv
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import uuid

ROOT = Path(__file__).resolve().parents[1]
IDENTITY = ("state", "district", "market", "commodity", "variety", "grade")
PRICES = ("min_price", "modal_price", "max_price")
TABLES = ("series", "observations", "policy_versions", "policies", "forecasts", "models", "evaluations", "ingestions")


def json_text(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256(path):
    with Path(path).open("rb") as source:
        return hashlib.file_digest(source, "sha256").hexdigest()


def series_id(identity):
    if set(identity) != set(IDENTITY) or any(not isinstance(v, str) or not v.strip() for v in identity.values()):
        raise ValueError("An exact six-field identity is required")
    return hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:16]


def decimal_positive(value):
    try:
        number = Decimal(str(value))
        return int(number.is_finite() and number > 0)
    except (InvalidOperation, ValueError):
        return 0


def decimal_le(left, right):
    try:
        a, b = Decimal(str(left)), Decimal(str(right))
        return int(a.is_finite() and b.is_finite() and a <= b)
    except InvalidOperation:
        return 0


def iso_date(value):
    try:
        return int(isinstance(value, str) and date.fromisoformat(value).isoformat() == value)
    except (ValueError, TypeError):
        return 0


def iso_timestamp(value):
    try:
        stamp = datetime.fromisoformat(value)
        return int(stamp.tzinfo is not None and stamp.utcoffset() is not None)
    except (ValueError, TypeError):
        return 0


def database_path(url=None):
    url = url if url is not None else os.environ.get("DATABASE_URL", "sqlite:///data/agrisense.db")
    if not url.startswith("sqlite:///"):
        raise ValueError("Only local sqlite:/// URLs are supported; other engines require a future adapter")
    location = url[len("sqlite:///"):]
    if location == ":memory:":
        return location
    if not location or "?" in location or "#" in location:
        raise ValueError("SQLite URL requires a plain local path without query or fragment")
    path = Path(location)
    return path if path.is_absolute() else ROOT / path


class Repository:
    def __init__(self, url=None):
        self.path = database_path(url)
        if isinstance(self.path, Path):
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        for name, count, function in [("decimal_positive", 1, decimal_positive), ("decimal_le", 2, decimal_le),
                                       ("iso_date", 1, iso_date), ("iso_timestamp", 1, iso_timestamp)]:
            self.connection.create_function(name, count, function, deterministic=True)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.connection.close()

    @contextmanager
    def transaction(self):
        self.connection.execute("SAVEPOINT operation")
        try:
            yield
        except BaseException:
            self.connection.execute("ROLLBACK TO operation")
            self.connection.execute("RELEASE operation")
            raise
        else:
            self.connection.execute("RELEASE operation")

    def initialize(self):
        if self.connection.in_transaction:
            raise ValueError("Initialize schema before starting ingestion transactions")
        exists = self.connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_info'").fetchone()
        if exists and [r[0] for r in self.connection.execute("SELECT version FROM schema_info")] != [1]:
            raise ValueError("Unsupported schema version; no automatic migration attempted")
        schema = (Path(__file__).parent / "schema.sql").read_text(encoding="utf-8")
        try:
            self.connection.executescript("BEGIN IMMEDIATE;\n" + schema + "\nCOMMIT;")
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def _put(self, table, values, keys):
        if table not in TABLES:
            raise ValueError("Invalid internal table")
        allowed = {r[1] for r in self.connection.execute(f"PRAGMA table_info({table})")}
        if not set(values).issubset(allowed) or not set(keys).issubset(values):
            raise ValueError("Invalid internal columns")
        where = " AND ".join(f"{k}=?" for k in keys)
        old = self.connection.execute(f"SELECT * FROM {table} WHERE {where}", [values[k] for k in keys]).fetchone()
        if old:
            if any(old[k] != v for k, v in values.items()):
                raise ValueError(f"Conflicting immutable {table} record; import rolled back")
            return
        columns = ",".join(values)
        marks = ",".join("?" for _ in values)
        self.connection.execute(f"INSERT INTO {table} ({columns}) VALUES ({marks})", list(values.values()))

    def track(self, path, kind, count):
        path = Path(path)
        try:
            name = path.resolve().relative_to(ROOT).as_posix()
        except ValueError:
            name = path.name
        self._put("ingestions", {"source_sha256": sha256(path), "source_path": name, "kind": kind, "row_count": count}, ["source_sha256"])

    def import_observations(self, path):
        count, known = 0, set()
        checksum = sha256(path)
        with self.transaction(), Path(path).open(encoding="utf-8", newline="") as source:
            reader = csv.DictReader(source)
            expected = {"date", *IDENTITY, *PRICES, "price_unit", "source_sha256", "source_record"}
            if set(reader.fieldnames or []) != expected or len(reader.fieldnames) != len(expected):
                raise ValueError("Cleaned CSV schema differs")
            for row in reader:
                if None in row or any(v is None for v in row.values()):
                    raise ValueError("Malformed CSV row")
                identity = {k: row[k] for k in IDENTITY}
                sid = series_id(identity)
                if sid not in known:
                    self._put("series", {"series_id": sid, **identity, "price_unit": row["price_unit"]}, ["series_id"])
                    known.add(sid)
                elif row["price_unit"] != "INR/quintal":
                    raise ValueError("Conflicting observation price unit")
                self._put("observations", {"series_id": sid, "date": row["date"], **{k: row[k] for k in PRICES},
                                           "source_sha256": row["source_sha256"], "source_record": int(row["source_record"])}, ["series_id", "date"])
                count += 1
            if not count or checksum != sha256(path):
                raise ValueError("Empty or changed source during import")
            self.track(path, "cleaned_observations", count)
        return count

    def import_policy(self, path):
        config = json.loads(Path(path).read_text(encoding="utf-8"))
        version = config["evaluation_version"]
        if config["schema_version"] != 1 or config["unit"] != "INR/quintal" or not config["series"]:
            raise ValueError("Unsupported policy schema/unit")
        with self.transaction():
            old = self.connection.execute("SELECT version FROM policy_versions WHERE active=1").fetchone()
            if old and old[0] != version:
                raise ValueError("Activating another policy requires an explicit future migration")
            self._put("policy_versions", {"version": version, "source_sha256": sha256(path), "config_json": json_text(config), "active": 1}, ["version"])
            seen = set()
            for entry in config["series"]:
                identity, sid = entry["identity"], entry["series_id"]
                existing = self.get_series(sid)
                if sid != series_id(identity) or not existing or any(existing[k] != identity[k] for k in IDENTITY):
                    raise ValueError("Policy references unknown/mismatched exact identity")
                if sid in seen or entry["evaluation_version"] != version:
                    raise ValueError("Duplicate or inconsistent policy entry")
                seen.add(sid)
                self._put("policies", {"series_id": sid, "version": version, **{k: entry[k] for k in
                          ["selected_method", "window", "minimum_history", "fallback_method", "benchmark_mae", "status"]}}, ["series_id", "version"])
            self.track(path, "forecast_policy", len(seen))
        return len(seen)

    def get_series(self, sid):
        return self._one("SELECT * FROM series WHERE series_id=?", (sid,))

    def find_series(self, identity):
        series_id(identity)
        return self._one("SELECT * FROM series WHERE state=? AND district=? AND market=? AND commodity=? AND variety=? AND grade=?", tuple(identity[k] for k in IDENTITY))

    def _one(self, sql, args=()):
        row = self.connection.execute(sql, args).fetchone()
        return dict(row) if row else None

    def _many(self, sql, args=()):
        return [dict(row) for row in self.connection.execute(sql, args)]

    def supported_series(self):
        return self._many("SELECT s.* FROM series s JOIN policies p USING(series_id) JOIN policy_versions v ON v.version=p.version WHERE v.active=1 ORDER BY s.series_id")

    def get_observations(self, sid, start=None, end=None):
        for bound in [start, end]:
            if bound is not None and not iso_date(bound):
                raise ValueError("Date bounds must be ISO dates")
        if start and end and start > end:
            raise ValueError("Reversed date range")
        return self._many("SELECT * FROM observations WHERE series_id=? AND (? IS NULL OR date>=?) AND (? IS NULL OR date<=?) ORDER BY date", (sid, start, start, end, end))

    def get_latest_observations(self, sid, n, cutoff=None):
        if type(n) is not int or n < 1 or (cutoff is not None and not iso_date(cutoff)):
            raise ValueError("Expected positive integer limit and optional ISO cutoff")
        return self._many("SELECT * FROM (SELECT * FROM observations WHERE series_id=? AND (? IS NULL OR date<=?) ORDER BY date DESC LIMIT ?) ORDER BY date", (sid, cutoff, cutoff, n))

    def get_latest_observation(self, sid, cutoff=None):
        rows = self.get_latest_observations(sid, 1, cutoff)
        return rows[0] if rows else None

    def get_policy(self, sid):
        return self._one("SELECT p.* FROM policies p JOIN policy_versions v ON p.version=v.version WHERE p.series_id=? AND v.active=1", (sid,))

    def load_policy(self):
        row = self._one("SELECT config_json FROM policy_versions WHERE active=1")
        return json.loads(row["config_json"]) if row else None

    def save_forecast(self, *, identity, status, prediction=None, method=None, policy_version=None,
                      history_cutoff=None, target_date=None, generated_at=None, forecast_id=None, details=None):
        sid = series_id(identity)
        series = self.get_series(sid)
        if series is None and status != "unsupported_series":
            raise ValueError("Unknown identity must use unsupported_series state")
        if policy_version is not None and not self._one("SELECT 1 FROM policies WHERE series_id=? AND version=?", (sid, policy_version)):
            raise ValueError("Unknown policy version for this exact series")
        if status in ("available", "fallback"):
            policy = self._one("SELECT * FROM policies WHERE series_id=? AND version=?", (sid, policy_version))
            expected = policy and policy["fallback_method" if status == "fallback" else "selected_method"]
            if method != expected or expected is None:
                raise ValueError("Forecast method does not match its referenced policy")
            if not self._one("SELECT 1 FROM observations WHERE series_id=? AND date=?", (sid, history_cutoff)):
                raise ValueError("History cutoff must identify a stored exact-series observation")
        stamp = generated_at or datetime.now(timezone.utc).isoformat()
        if not iso_timestamp(stamp):
            raise ValueError("Generation timestamp must include timezone")
        stamp = datetime.fromisoformat(stamp).astimezone(timezone.utc).isoformat()
        if history_cutoff is not None and history_cutoff > stamp[:10]:
            raise ValueError("History cutoff cannot follow generation date")
        identifier = forecast_id or str(uuid.uuid4())
        with self.transaction():
            self._put("forecasts", {"forecast_id": identifier, "series_id": sid if series else None,
                      "requested_identity_json": json_text(identity), "target_date": target_date, "generated_at": stamp,
                      "prediction": None if prediction is None else str(prediction), "method": method,
                      "policy_version": policy_version, "status": status, "history_cutoff": history_cutoff,
                      "details_json": json_text(details or {})}, ["forecast_id"])
        return self._one("SELECT * FROM forecasts WHERE forecast_id=?", (identifier,))

    def forecast_history(self, sid):
        return self._many("SELECT * FROM forecasts WHERE series_id=? ORDER BY generated_at, forecast_id", (sid,))

    def get_forecast(self, forecast_id):
        return self._one("SELECT * FROM forecasts WHERE forecast_id=?", (forecast_id,))

    def get_models(self):
        return self._many("SELECT * FROM models ORDER BY model_id")

    def get_evaluations(self, sid=None):
        return self._many("SELECT * FROM evaluations WHERE (? IS NULL OR series_id=?) ORDER BY evaluation_id", (sid, sid))

    def summary(self):
        counts = {name: self.connection.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in TABLES}
        integrity = self.connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_keys = self._many("PRAGMA foreign_key_check")
        return {"schema_version": self.connection.execute("SELECT version FROM schema_info").fetchone()[0],
                "table_counts": counts, "date_range": self._one("SELECT min(date) AS first_date,max(date) AS last_date FROM observations"),
                "commodity_counts": self._many("SELECT s.commodity,count(*) AS observations FROM observations o JOIN series s USING(series_id) GROUP BY s.commodity ORDER BY s.commodity"),
                "policy_methods": self._many("SELECT p.selected_method,count(*) AS series FROM policies p JOIN policy_versions v USING(version) WHERE v.active=1 GROUP BY p.selected_method ORDER BY p.selected_method"),
                "active_policy_series": len(self.supported_series()), "duplicate_observations": self.connection.execute("SELECT count(*) FROM (SELECT series_id,date FROM observations GROUP BY series_id,date HAVING count(*)>1)").fetchone()[0],
                "foreign_keys_enabled": bool(self.connection.execute("PRAGMA foreign_keys").fetchone()[0]),
                "foreign_key_violations": foreign_keys, "integrity_check": integrity,
                "indexes": self._many("SELECT name,tbl_name FROM sqlite_master WHERE type='index' ORDER BY name")}
