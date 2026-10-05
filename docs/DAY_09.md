# Day 9 — Database and persistence layer

Krishkumar | Roll No: 2401CS83 | IIT Patna  
Repository: https://github.com/Krish290107/agrisense

Status: complete. Downloads: none. Uses Python's existing sqlite3 module.

Run from the repository with the project interpreter:

```powershell
.\.venv\Scripts\python.exe scripts/init_database.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The importer initializes version 1, verifies protected sources, imports observations/policy/metadata, imports them again to prove idempotency, verifies every price/provenance row and policy query, and writes the [database summary](../reports/data/database_summary.json) and [report](../reports/data/DATABASE_REPORT.md). It never deletes the database to achieve repeatability. Conflicting existing records fail and roll back; identical records are retained. No production forecasts are generated.

The default `data/agrisense.db` and its SQLite sidecars are ignored. Optional process environment `DATABASE_URL` or CLI `--database-url` supports `sqlite:///relative/path.db`, a local absolute SQLite path, or `sqlite:///:memory:` for tests. Relative paths resolve from repository root, not the current working directory. The CLI does not load a private `.env`; no configuration is required for the default. `backend/.env.example` documents the optional setting for later integration. Non-SQLite schemes fail explicitly and never echo credentials. An alternate database path is trusted local configuration, not a public request input; users choosing alternate runtime filenames should keep them out of source control.

## Stored artifacts

| Entity | Rows | Purpose |
|---|---:|---|
| series | 229 | Exact state/district/market/commodity/variety/grade identity |
| observations | 39,630 | Valid canonical prices, dates and source provenance |
| policy_versions / policies | 1 / 9 | Unchanged Day 8 JSON and normalized active policy |
| models | 1 | Experimental bundle path/hash, feature schema and configuration metadata |
| evaluations | 405 | 126 Day 5, nine Day 7 and 270 Day 8 window metrics |
| ingestions | 7 | Source hashes, artifact paths, kinds and logical row counts |
| forecasts | 0 | Ready for future forecasts and explicit failure states |

Dates span **2024-01-01–2025-12-29**. Commodity observations: Onion 12,666; Potato 13,000; Tomato 13,964. All nine policy candidates resolve and retain their original methods: seven naive and two rolling mean 7. ML stays `experimental_not_selected`.

## Day 10 integration contract

Import `Repository` from `database.store` and use its context manager to close connections. `initialize()` is idempotent and must run before ingestion transactions. `transaction()` supports nested savepoints. The single CLI wraps all artifact imports and verification in one transaction; initial schema creation is separately atomic. Failure may leave an empty valid schema, never a partially imported dataset.

Methods include `find_series(identity)`, `get_series(id)`, `supported_series()`, `get_observations(id, start, end)`, `get_latest_observations(id, n, cutoff)`, `get_latest_observation(id, cutoff)`, `get_policy(id)`, `load_policy()`, `save_forecast(...)`, `get_forecast(id)`, `forecast_history(id)`, `get_models()` and `get_evaluations(id)`. Date bounds/cutoffs are inclusive ISO dates. Latest-N selects only one exact series and returns the selected records oldest to newest. Unknown history returns an empty list/None, never another series' data.

Observation and forecast prices are decimal strings, preserving arbitrary precision and trailing zeros. Convert explicitly to Decimal for arithmetic. Centralized connections register deterministic decimal/date functions used by database CHECK constraints. External tools may read prices; direct writes require the same functions and otherwise fail. Foreign keys are enabled for every repository connection. Schema/index definitions are in [schema.sql](../database/schema.sql); price/identity constraints are tested independently of application validation.

`save_forecast` requires the requested exact identity and status. Available/fallback records require a positive prediction, matching policy method/version and an existing same-series history cutoff. A provided target date must follow that cutoff; it can be null for next-observed-record predictions. Generated timestamps include timezone and normalize to UTC. Missing-history/error/unsupported results use null prediction/method, never zero. Unknown identities may be recorded as unsupported requests with their requested identity JSON and no foreign-key series. Caller-supplied forecast IDs provide retry idempotency; otherwise UUIDs identify separate requests. Existing forecasts survive artifact reimports. Day 10 remains responsible for actual forecast computation and proving the supplied cutoff matches the information used.

Policy versions and historical observations are immutable to this importer. A new active policy or corrections require an explicit future migration/reconciliation, not a silent upsert. Schema versions other than 1 are rejected. SQLite is local persistence; PostgreSQL portability requires a future adapter/migration, and no cloud database or production concurrency infrastructure is claimed.

## Verification

Ten focused tests and 61 existing tests pass. Tests cover schema/foreign keys/unique keys, decimal/date constraints, exact market/variety/grade separation, import rollback and conflicts, repeated import counts, latest-seven ordering/cutoff, policy reload and unknown identities, forecast storage/null statuses, metadata ingestion, deterministic summaries and file-backed reopening. All tests use temporary or in-memory databases.

Real execution verifies 39,630 exact price/provenance roundtrips, all nine policy query contracts, zero duplicate observations, SQLite integrity and foreign-key checks, repeated counts, deterministic summary/report output and protected historical hashes. No source datasets, Day 3–8 outputs, model binaries, scientific policy, existing API or frontend behavior were changed. No files were removed.

Next: Day 10 forecast-service logic and FastAPI prediction endpoints.
