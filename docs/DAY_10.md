# Day 10 — Forecast service and FastAPI

Krishkumar | Roll No: 2401CS83 | IIT Patna  
Repository: https://github.com/Krish290107/agrisense

Status: complete. No downloads, new dependencies, database migration or frontend changes.

The [API report](../reports/data/FORECAST_API_REPORT.md) documents endpoints, semantics and verification. The [machine-readable summary](../reports/data/forecast_api_summary.json) records methods, tests and real-data smoke results.

`backend/forecast_service.py` provides HTTP-independent logic. `backend/forecast_api.py` contains Pydantic schemas and versioned routes, registered by the existing app. The repository adds optional existing-file/read-only connection modes and immediate transactions without changing its default behavior. Health, documentation styling and configured CORS origins remain; POST is permitted for forecast requests.

Use `GET /api/v1/forecast/series` to obtain a supported stable ID, then `POST /api/v1/forecast` with `series_id` and optional `as_of_date`. Only these fields are accepted. Read prices through `/api/v1/forecast/series/{series_id}/history`, and saved results through `/api/v1/forecast/series/{series_id}/forecasts`. Limits are bounded and documented in `/docs`.

The service supports only `next_observation`: seven naive and two rolling-mean-7 policies. Decimal-string prices avoid binary floating-point artifacts. Rolling predictions round explicitly to six fractional places, half-even; naive prices retain original precision. Missing rolling history falls back to the latest valid price; no history yields null. No ML, arbitrary calendar targets, interpolation or confidence scores are exposed. Historical benchmark MAE is context, not an uncertainty interval.

Requests with equivalent history, policy, calculation version and as-of date reuse the saved forecast and its original timestamp. Only successful forecasts are stored. Dry-run callers use `generate_forecast(repo, sid, persist=False)`; verification additionally opens the database read-only. As-of dates use the current policy with earlier observations, not the policy available historically. Future as-of dates cannot include observations beyond today UTC.

Readiness is checked on forecast access; missing, empty or incompatible storage produces a concise 503 and never implicitly creates an empty database. No automatic bulk imports occur. Each request owns a connection in its worker; immediate transactions serialize concurrent saves. The existing Day 9 initializer remains the explicit preparation workflow.

Verification: **14 focused + 71 regression tests passed**. Tests use temporary databases and real ASGI dispatch. All nine real series calculate correctly without persistence; read endpoints and OpenAPI work; the real database stays byte-identical with zero forecasts; 90 protected historical paths retain their hashes. No files were removed.

Local SQLite is not durable serverless storage; future hosting needs durable persistence. Latest candidate data is from November 2025, and this policy is not a validated fixed-horizon forecast. Day 11 should display cutoffs and next-observation semantics clearly.
