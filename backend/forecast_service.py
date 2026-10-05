"""Exact-series, next-observation forecasting; no HTTP or ML dependencies."""

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal, localcontext, ROUND_HALF_EVEN
import hashlib
import json
import logging
import sqlite3

from database.store import Repository, IDENTITY, decimal_positive, iso_date, json_text

LOGGER = logging.getLogger("agrisense.forecast")
CALCULATION_VERSION = "day10-decimal-v1"


class SeriesNotFound(Exception):
    pass


class ForecastUnavailable(Exception):
    pass


@contextmanager
def open_repository(url=None, *, read_only=False):
    try:
        with Repository(url, must_exist=True, read_only=read_only) as repo:
            version = repo.connection.execute("SELECT version FROM schema_info").fetchall()
            tables = {r[0] for r in repo.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if [r[0] for r in version] != [1] or not {"series", "observations", "policies", "policy_versions", "forecasts"}.issubset(tables):
                raise ForecastUnavailable()
            if not repo.connection.execute("SELECT 1 FROM observations LIMIT 1").fetchone() or not repo.supported_series():
                raise ForecastUnavailable()
            yield repo
    except (sqlite3.Error, OSError, ValueError, KeyError, TypeError, ForecastUnavailable):
        LOGGER.warning("Forecast database unavailable or invalid; verify the Day 9 import before serving requests")
        raise ForecastUnavailable() from None


def require_series(repo, sid):
    series = repo.get_series(sid)
    if series is None:
        raise SeriesNotFound()
    return series


def validate_policy(policy):
    method = policy["selected_method"]
    if (method not in {"naive", "rolling_mean_7"} or policy["fallback_method"] != "naive"
            or policy["status"] != "selected"
            or policy["minimum_history"] != (7 if method == "rolling_mean_7" else 1)
            or policy["window"] != (7 if method == "rolling_mean_7" else None)):
        raise ForecastUnavailable()


def supported_series(repo):
    result = []
    for series in repo.supported_series():
        policy = repo.get_policy(series["series_id"])
        validate_policy(policy)
        result.append({**series, "selected_method": policy["selected_method"], "policy_version": policy["version"]})
    return result


def rolling_mean(prices):
    numbers = [Decimal(price) for price in prices]
    with localcontext() as context:
        integers = max(max(n.adjusted() + 1, 1) for n in numbers)
        fractional = max(max(-n.as_tuple().exponent, 0) for n in numbers)
        context.prec = max(28, integers + fractional + 20)
        value = (sum(numbers) / Decimal(len(numbers))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_EVEN)
    if value <= 0:
        raise ForecastUnavailable()
    return format(value, "f")


def generate_forecast(repo, sid, *, as_of_date=None, persist=True):
    if as_of_date is not None and not iso_date(as_of_date):
        raise ValueError("as_of_date must be an ISO date")
    with repo.transaction(immediate=persist):
        series = require_series(repo, sid)
        policy = repo.get_policy(sid)
        generated_at = datetime.now(timezone.utc).isoformat()
        effective_cutoff = min(as_of_date or generated_at[:10], generated_at[:10])
        result = {"status": "unsupported_series", "forecast_id": None, "series": series,
                  "price_unit": series["price_unit"], "forecast_type": "next_observation", "prediction": None,
                  "selected_method": None, "method_used": None, "window": None, "fallback_used": False,
                  "history_observations_used": 0, "history_start_date": None, "history_cutoff_date": None,
                  "latest_observed_price": None, "latest_observation_date": None, "generated_at": generated_at,
                  "as_of_date": as_of_date, "policy_version": None, "historical_benchmark_mae": None,
                  "calculation_version": CALCULATION_VERSION}
        if not policy:
            LOGGER.info("Forecast unsupported series=%s", sid)
            return result
        validate_policy(policy)
        result.update(selected_method=policy["selected_method"], window=policy["window"],
                      policy_version=policy["version"], historical_benchmark_mae=policy["benchmark_mae"])
        history = repo.get_latest_observations(sid, policy["minimum_history"], cutoff=effective_cutoff)
        if not history:
            result["status"] = "insufficient_history"
            LOGGER.info("Forecast insufficient history series=%s", sid)
            return result
        if any(r["series_id"] != sid or not iso_date(r["date"]) or r["date"] > effective_cutoff
               or not decimal_positive(r["modal_price"]) for r in history):
            raise ForecastUnavailable()
        if [r["date"] for r in history] != sorted({r["date"] for r in history}):
            raise ForecastUnavailable()
        fallback = len(history) < policy["minimum_history"]
        method = "naive" if fallback else policy["selected_method"]
        used = history[-1:] if method == "naive" else history
        prediction = used[-1]["modal_price"] if method == "naive" else rolling_mean([r["modal_price"] for r in used])
        result.update(status="ok", prediction=prediction, method_used=method, fallback_used=fallback,
                      history_observations_used=len(used), history_start_date=used[0]["date"],
                      history_cutoff_date=used[-1]["date"], latest_observation_date=used[-1]["date"],
                      latest_observed_price=used[-1]["modal_price"])
        fingerprint = hashlib.sha256(json_text({"calculation_version": CALCULATION_VERSION, "series_id": sid,
                          "policy": policy, "as_of_date": as_of_date,
                          "history": [{"date": row["date"], "modal_price": row["modal_price"]} for row in used],
                          "method_used": method}).encode()).hexdigest()
        if not persist:
            return result
        previous = repo.get_forecast(fingerprint)
        if previous:
            saved = json.loads(previous["details_json"])
            if (previous["prediction"] != prediction or previous["history_cutoff"] != used[-1]["date"]
                    or saved.get("calculation_version") != CALCULATION_VERSION):
                raise ForecastUnavailable()
            return saved
        result["forecast_id"] = fingerprint
        try:
            repo.save_forecast(identity={k: series[k] for k in IDENTITY}, status="fallback" if fallback else "available",
                               prediction=prediction, method=method, policy_version=policy["version"],
                               history_cutoff=used[-1]["date"], generated_at=generated_at,
                               forecast_id=fingerprint, details=result)
        except (sqlite3.Error, ValueError):
            LOGGER.warning("Forecast persistence failed series=%s", sid)
            raise ForecastUnavailable() from None
        LOGGER.info("Forecast generated series=%s method=%s fallback=%s", sid, method, fallback)
        return result


def forecast_history(repo, sid, limit):
    require_series(repo, sid)
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError("Forecast history limit must be between 1 and 100")
    return repo._many("SELECT forecast_id,generated_at,prediction,method,policy_version,status,history_cutoff "
                      "FROM forecasts WHERE series_id=? ORDER BY generated_at DESC,forecast_id DESC LIMIT ?", (sid, limit))
