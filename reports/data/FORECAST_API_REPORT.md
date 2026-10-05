# Day 10 — Forecast service and prediction API

Krishkumar | Roll No: 2401CS83 | IIT Patna  
Repository: https://github.com/Krish290107/agrisense

Status: complete. Downloads and new dependencies: none. The service uses SQLite schema v1 and the active Day 8 policy. Nine forecast-supported series are distinct from the 229 historical series.

## Forecast contract

Every estimate has `forecast_type: next_observation`: the next reported market price, not a validated 7-day, 30-day or arbitrary-date prediction. Seven policies use the latest observation; two use the mean of the latest seven observations, not calendar days. Exact six-field identities remain separate. Short rolling history uses naive fallback; zero history returns `insufficient_history` with null prediction. A known series without active policy returns `unsupported_series`; an unknown ID returns HTTP 404. ML remains experimental and is never loaded by the service.

Prices are decimal strings. Naive preserves source precision; rolling means use Decimal arithmetic and explicitly round to six fractional places using ROUND_HALF_EVEN. No whole-rupee rounding, interpolation, fabricated zeros, confidence scores or uncertainty bands are introduced. `historical_benchmark_mae` is past benchmark context only, not an individual error guarantee. Results identify the selected and actual method, fallback flag, number/period of observations used, latest price/date, history cutoff, policy version and calculation version.

Optional `as_of_date` filters history inclusively and is capped at today's UTC date. It applies the **current active policy** to earlier observations; it does not reconstruct which policy was available then or establish an unbiased historical backtest. Requests cannot specify a target date or forecast horizon. Persisted target_date is null.

## Endpoints

| Method and path | Purpose |
|---|---|
| GET /health | Unchanged health contract, independent of database readiness |
| GET /api/v1/forecast/series | Active forecast-supported series, ordered by stable ID |
| GET /api/v1/forecast/series/{series_id}/history | Chronological recent prices; default 30, limit 1–365 |
| POST /api/v1/forecast | Generate/reuse and persist the active next-observation forecast |
| GET /api/v1/forecast/series/{series_id}/forecasts | Stored forecasts newest first; default 20, limit 1–100 |

POST accepts `series_id` (16 lowercase hexadecimal characters) and optional ISO `as_of_date`. Extra fields, malformed IDs, invalid dates and invalid limits return 422. Successful generation and domain unavailability use HTTP 200 with explicit status; unknown IDs use 404; database/policy/persistence failures use sanitized 503 responses. History can describe any known historical series and includes a `forecast_supported` flag. Observation provenance, filesystem paths and SQL are not exposed. Explicit Pydantic response schemas are available in `/docs`; the existing hidden OpenAPI-link styling remains.

## Persistence, readiness and concurrency

Each synchronous route opens and closes its own repository connection in the same worker thread. SQLite URI `mode=rw` requires an existing file and cannot silently create an empty database. Readiness checks schema v1, required tables, observations and active policies on access; `/health` stays available even if forecast storage is not ready. No startup/request imports, dataframe loading or model training occur. Read-only verification uses `mode=ro`.

Successful requests use an immediate transaction and a deterministic SHA-256 fingerprint over calculation version, exact series, normalized policy, requested as-of date, method and used history prices/dates. Equivalent retries return the original saved response, including its ID and generation timestamp. Changed history/policy/calculation/request cutoff produces a new fingerprint. The SQLite write reservation serializes low-scale concurrent retries; a test confirms one row from two concurrent requests. Generation failures roll back and never return success. Unsupported/insufficient-history requests are not stored. The Day 9 table records successful results as `available` or `fallback`; the generation response uses `ok` plus `fallback_used`. Stored history retains the original database status.

The existing repository received only optional existing-file/read-only connection modes and an immediate transaction option. Its schema, importer, default behavior and historical artifacts remain unchanged. The old Day 9 implementation hash describes that historical code version; it is not rewritten. Environment-based origins are preserved, with POST added to allowed CORS methods for the new endpoint. Logs record concise generation/fallback/unavailable/persistence events without histories or exception dumps.

## Verification

- **14 focused service/API tests and 71 prior regression tests passed (85 total).** HTTP tests invoke the actual FastAPI ASGI application using isolated temporary databases; no extra HTTP testing dependency is needed.
- Tests cover latest-seven 200–800 => 500, grade isolation, as-of exclusion, naive fallback, no history, unsupported/unknown IDs, decimal rounding, persistence/reuse/concurrent retries, read-only operation, invalid policy, sanitized persistence failures, bounded history, OpenAPI, health and CORS.
- Real non-persisting calculations pass for all **nine** active candidates: **seven naive, two rolling mean 7**, with sufficient history and no fallback. Repeated calculations agree. Dahod Onion: **1442.857143**, cutoff **2025-11-04**; Dahod Potato: **1428.571429**, cutoff **2025-11-03** (INR/quintal).
- Real GET smoke checks pass for health, discovery, each candidate's history/forecast-history and OpenAPI. Every generated test forecast used a temporary database; the real database stays byte-identical with **zero** forecast records.
- **90 protected historical paths verified unchanged**, including Day 3–8 inputs/results, Day 8 policy and Day 9 reports. Database integrity check passes. No historical datasets, model artifacts, scientific metrics or frontend files were modified.

## Limits and Day 11

The stored candidate observations end in November 2025; these are estimates from the latest imported history, not fresh live market data. Historical performance does not establish current accuracy. Local SQLite is suitable for this low-scale local service, not durable storage on ephemeral/serverless filesystems such as Vercel. Hosted persistence will require a durable external database or an appropriate persistent-volume deployment. Nothing is deployed today.

Day 11 can connect the dashboard to discovery, history, forecast generation and saved history while displaying the exact identity, source cutoff, decimal price, fallback state and next-observation limitation.
