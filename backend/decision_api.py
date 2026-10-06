"""Read-only comparisons from the active baseline forecast service."""

from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel

from backend.forecast_api import ForecastResult, unavailable
from backend.forecast_service import (ForecastUnavailable, SeriesNotFound, generate_forecast,
                                      open_repository, require_series, supported_series)

router = APIRouter(prefix="/api/v1/decision", tags=["Decision support"])


class ComparisonRow(BaseModel):
    forecast: ForecastResult
    difference: str | None
    percentage: str | None
    signal: Literal["above", "near", "below"] | None


class Comparison(BaseModel):
    selected_series_id: str
    scope: Literal["exact_variety_grade", "commodity"]
    warning: str | None
    markets: list[ComparisonRow]


def price_signal(latest, prediction):
    if latest is None or prediction is None:
        return {"difference": None, "percentage": None, "signal": None}
    latest, prediction = Decimal(latest), Decimal(prediction)
    if not latest.is_finite() or not prediction.is_finite() or latest <= 0 or prediction <= 0:
        return {"difference": None, "percentage": None, "signal": None}
    difference = prediction - latest
    percentage = difference / latest * 100
    # Fixed display rule, not tuned against historical outcomes; exactly 2% is not near.
    signal = "near" if abs(percentage) < 2 else "above" if difference > 0 else "below"
    return {"difference": format(difference, "f"), "percentage": format(percentage, "f"), "signal": signal}


def compare_markets(repo, selected_id):
    with repo.transaction():
        selected = require_series(repo, selected_id)
        candidates = [s for s in supported_series(repo) if s["commodity"] == selected["commodity"]]
        if not any(s["series_id"] == selected_id for s in candidates):
            raise HTTPException(422, detail={"code": "unsupported_series"})
        exact = [s for s in candidates if (s["variety"], s["grade"]) == (selected["variety"], selected["grade"])]
        is_exact = len({(s["district"], s["market"]) for s in exact}) >= 2
        rows = []
        for series in exact if is_exact else candidates:
            forecast = generate_forecast(repo, series["series_id"], persist=False)
            rows.append({"forecast": forecast, **price_signal(forecast["latest_observed_price"], forecast["prediction"])})
        rows.sort(key=lambda row: (row["forecast"]["prediction"] is None,
                                  -Decimal(row["forecast"]["prediction"] or "0"),
                                  row["forecast"]["series"]["series_id"]))
        return {"selected_series_id": selected_id, "scope": "exact_variety_grade" if is_exact else "commodity",
                "warning": None if is_exact else "Supported markets may contain different varieties or grades; compare with care.",
                "markets": rows}


@router.get("/markets", response_model=Comparison, summary="Compare active next-observation estimates without saving")
def markets(request: Request, series_id: Annotated[str, Query(pattern=r"^[0-9a-f]{16}$")]):
    try:
        with open_repository(getattr(request.app.state, "database_url", None), read_only=True) as repo:
            return compare_markets(repo, series_id)
    except SeriesNotFound:
        raise HTTPException(404, detail={"code": "series_not_found"}) from None
    except ForecastUnavailable:
        raise unavailable() from None
