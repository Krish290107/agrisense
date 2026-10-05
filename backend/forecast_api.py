"""Versioned forecast routes and their public contracts."""

from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.forecast_service import (ForecastUnavailable, SeriesNotFound, open_repository,
                                      supported_series, require_series, generate_forecast, forecast_history)
from database.store import iso_date

router = APIRouter(prefix="/api/v1/forecast", tags=["Forecasts"])
ERROR_RESPONSES = {404: {"description": "Exact series ID does not exist."},
                   503: {"description": "Forecast database or policy unavailable; no forecast was saved."}}
SeriesID = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
PathID = Annotated[str, Path(pattern=r"^[0-9a-f]{16}$")]
Price = Annotated[str, Field(description="Decimal string in INR/quintal; preserves price precision.")]


class Series(BaseModel):
    series_id: SeriesID
    state: str
    district: str
    market: str
    commodity: str
    variety: str
    grade: str
    price_unit: Literal["INR/quintal"]


class SupportedSeries(Series):
    selected_method: Literal["naive", "rolling_mean_7"]
    policy_version: str


class ForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    series_id: SeriesID
    as_of_date: str | None = Field(default=None, description="Apply the current policy using observations on/before this ISO date (capped at today UTC); not a forecast target date.")

    @field_validator("as_of_date")
    @classmethod
    def valid_date(cls, value):
        if value is not None and not iso_date(value):
            raise ValueError("Expected YYYY-MM-DD calendar date")
        return value


class ForecastResult(BaseModel):
    status: Literal["ok", "insufficient_history", "unsupported_series"]
    forecast_id: str | None
    series: Series
    price_unit: Literal["INR/quintal"]
    forecast_type: Literal["next_observation"]
    prediction: Price | None
    selected_method: Literal["naive", "rolling_mean_7"] | None
    method_used: Literal["naive", "rolling_mean_7"] | None
    window: int | None
    fallback_used: bool
    history_observations_used: int
    history_start_date: str | None
    history_cutoff_date: str | None
    latest_observed_price: Price | None
    latest_observation_date: str | None
    generated_at: str
    as_of_date: str | None
    policy_version: str | None
    historical_benchmark_mae: float | None = Field(description="Historical benchmark context, not a calibrated error bound for this forecast.")
    calculation_version: str


class Observation(BaseModel):
    date: str
    min_price: Price
    modal_price: Price
    max_price: Price


class HistoryResult(BaseModel):
    series: Series
    forecast_supported: bool
    observations: list[Observation]


class StoredForecast(BaseModel):
    forecast_id: str
    generated_at: str
    prediction: Price | None
    method: str | None
    policy_version: str | None
    status: Literal["available", "fallback", "insufficient_history", "unsupported_series", "error"]
    history_cutoff: str | None


def database(request):
    return open_repository(getattr(request.app.state, "database_url", None))


def unavailable():
    return HTTPException(503, detail={"code": "database_unavailable", "message": "Forecast storage unavailable. Verify the Day 9 database import."})


@router.get("/series", response_model=list[SupportedSeries], summary="List active forecast-supported series", responses={503: ERROR_RESPONSES[503]})
def list_series(request: Request):
    try:
        with database(request) as repo:
            return supported_series(repo)
    except ForecastUnavailable:
        raise unavailable() from None


@router.get("/series/{series_id}/history", response_model=HistoryResult, summary="Read chronological recent observations", responses=ERROR_RESPONSES)
def history(request: Request, series_id: PathID, limit: Annotated[int, Query(ge=1, le=365)] = 30):
    try:
        with database(request) as repo:
            series = require_series(repo, series_id)
            return {"series": series, "forecast_supported": repo.get_policy(series_id) is not None,
                    "observations": repo.get_latest_observations(series_id, limit)}
    except SeriesNotFound:
        raise HTTPException(404, detail={"code": "series_not_found"}) from None
    except ForecastUnavailable:
        raise unavailable() from None


@router.post("", response_model=ForecastResult, summary="Generate and save a next-observation estimate",
             responses=ERROR_RESPONSES,
             description="Uses the active baseline policy. No calendar target or fixed-day horizon is supported. Equivalent requests reuse their saved forecast.")
def forecast(request: Request, body: ForecastRequest):
    try:
        with database(request) as repo:
            return generate_forecast(repo, body.series_id, as_of_date=body.as_of_date)
    except SeriesNotFound:
        raise HTTPException(404, detail={"code": "series_not_found"}) from None
    except ForecastUnavailable:
        raise unavailable() from None


@router.get("/series/{series_id}/forecasts", response_model=list[StoredForecast], summary="Read recent stored forecasts, newest first", responses=ERROR_RESPONSES)
def stored_forecasts(request: Request, series_id: PathID, limit: Annotated[int, Query(ge=1, le=100)] = 20):
    try:
        with database(request) as repo:
            return forecast_history(repo, series_id, limit)
    except SeriesNotFound:
        raise HTTPException(404, detail={"code": "series_not_found"}) from None
    except ForecastUnavailable:
        raise unavailable() from None
