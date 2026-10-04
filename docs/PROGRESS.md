# AgriSense progress

**Project owner:** Krishkumar

**Roll No:** 2401CS83

**Institution:** IIT Patna

**GitHub repository:** https://github.com/Krish290107/agrisense

**Updated:** October 4, 2026 (Asia/Calcutta)

## Day 3 status: complete

The canonical cleaned CSV contains **39,630 rows across 229 separate series**, spanning **2024-01-01 through 2025-12-29** (704 observed dates). From 39,634 selected observations, the pipeline quarantined three invalid-price rows and removed one exact duplicate. Zero conflicting keys, invalid dates, numeric failures or missing identity rows were found. Commodity totals: Onion 12,666; Potato 13,000; Tomato 13,964. FAQ (36,440 rows) and Non-FAQ (2,977 rows) remain separate alongside the other source grades.

The three invalid observations were inspected: Jamnagar Onion on 2024-02-07 has minimum price zero; Rajkot (Veg.Sub Yard) Potato on 2024-03-09 and Ahmedabad (Chimanbhai Patal Market Vasana) Potato on 2025-07-16 have maximum price zero. The latter two also violate price ordering. No corrected prices were invented. The exact duplicate is Gondal (Veg.market Gondal) APMC Tomato, Local grade, on 2025-12-28. All four exclusions retain original field values and source record references in the local audit.

Verification: nine Day 3 tests and all 14 Day 2 regression tests pass. Independent output checks confirm positive ordered prices, valid dates, unique keys, deterministic sorting, row accounting and exactly the original 229 distinct series. Backend import, health handler, OpenAPI and docs smoke checks pass; frontend/backend and deployment files have no changes. Documentation links, ignore protections, Python compilation, dependency consistency and diff whitespace checks pass. The real pipeline ran twice; cleaned CSV, rejected-row CSV, JSON summary and Markdown report were byte-identical. Both original hashes match the Day 2 provenance before and after the rerun.

Removed two obsolete setup guides and repaired their links; required files, framework-generated agent guidance, active runtime helpers, tests, configurations and raw data remain. No dependencies were added. See [Day 3](DAY_03.md), [cleaning summary](../reports/data/cleaning_summary.json) and [cleaning report](../reports/data/CLEANING_REPORT.md).

## Day 2 status: complete with an explicit history limitation

The project state is **Gujarat**. The supplied real Kaggle files have been imported, profiled and documented. No observations were fabricated, production-cleaned, or silently merged. The original two-year same-series target is unmet; an explicitly provisional shorter-history scope is supplied instead.

Source: [Daily Commodity Prices India](https://www.kaggle.com/datasets/khandelwalmanas/daily-commodity-prices-india), republished by Manas Khandelwal. Public Kaggle metadata was accessed successfully and identifies INR/quintal price units, ISO dates, upstream OGD provenance, and prior cleaning/deduplication. Its license field is Other while its description states GODL-India; that distinction is recorded. The user-supplied files' exact Kaggle release and original acquisition time remain unknown.

### Completed changes

- Added the separate local `requirements-data.txt` with pandas 3.0.6 in the existing Python 3.13.10 `.venv`; backend dependencies are unchanged.
- Added `configs/data_sources.json` with Kaggle provenance, source checks, mappings and Gujarat scope policy.
- Completed the importer/profiler and shared utilities. Fixed full-file memory loading with chunked scanning/streaming hashes and copies. Fixed rejection of originals already under `data/raw`; managed bundle folders are excluded from discovery.
- Created per-file, checksum-verified, immutable CSV/provenance bundles while preserving `data/raw/2024.csv` and `2025.csv`.
- Generated compact real-data reports and a 15-combination recommendation. Full per-series coverage and small samples remain local and ignored.
- Added `docs/DAY_02.md`, `DATA_SOURCES.md`, `DATA_DICTIONARY.md`; updated README and this progress record.
- Added 14 meaningful offline tests using a separately labeled synthetic fixture. Those invented test values are never imported into the real dataset or used in its reported statistics.
- Preserved the working frontend/backend, deployment configuration and source files. No GitHub push or Vercel changes performed.

### Actual real-data results

| Measurement | Result |
| --- | --- |
| 2024 original | 5,544,500 rows; 2024-01-01 to 2024-12-31; 366 distinct dates |
| 2025 original | 5,819,482 rows; 2025-01-01 to 2025-12-30; 342 distinct dates |
| Combined originals | 11,363,982 rows, 1,106,091,120 bytes; all dates parse under `%Y-%m-%d` |
| Gujarat across all commodities | 523,868 rows; 2024-01-01 to 2025-12-29; 707 distinct dates |
| Gujarat Onion / Potato / Tomato | 12,667 / 13,002 / 13,965 rows; 39,634 total |
| Detailed selected-subset series | 229, identified by state/district/market/commodity/variety/grade |
| Date and numeric parse failures in selected subset | 0 |
| Exact duplicates / repeated candidate keys | 1 beyond-first duplicate / 1 repeated key |
| Conflicting candidate keys | 0 |
| Nonpositive prices | 1 minimum-price value and 2 maximum-price values; modal prices all positive |
| Price-order violations | 2 rows; nonpositive/order flags affect 3 distinct series |
| Units | INR/quintal from publisher declaration; no row-level unit fields; arrivals absent |
| Original 700-day span screen | 0 qualifying series; maximum unchanged-identity span is 675 days |
| Explicit shorter-history option | 600-day minimum span; 60 eligible series; 15 selected combinations, five per commodity |
| Recommended series | 516-633 observation days; 76.4%-94.1% calendar coverage; longest internal gaps 3-18 days |

Recommended markets: Dahod (Veg. Market), Bilimora and Kapadvanj for all three commodities; Nadiyad (Piplag) for Onion/Tomato; Navsari for Tomato; Ankleshwar and Nadiad for Potato; Morbi for Onion. Exact variety/grade/date identities are in [recommended_scope.csv](../reports/data/recommended_scope.csv). All selected grades are FAQ; different varieties remain separate.

Later records contain changed market strings such as APMC suffixes, sometimes with changed varieties/grades. No identity equivalence is assumed. This explains why pooled state/commodity dates can extend beyond the longest unchanged series; further source-label investigation belongs to Day 3. The incomplete 2025 date set is not treated as zero prices.

### Actual commands and verification

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe scripts\import_market_data.py data\raw --source kaggle_daily_india --kind historical --date-format "%Y-%m-%d"
.\.venv\Scripts\python.exe scripts\profile_market_data.py --state Gujarat --commodities Onion Potato Tomato
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_market_data.py" -v
.\.venv\Scripts\python.exe -m pip check
```

- Import: both real files successfully imported, originals/copies checksum-verified. Repeat import returned `duplicate_skipped` for both with original provenance retained.
- Real profile: success, reports contain measured data and the explicit shorter-history limitation. Human-readable tables were refreshed from the verified aggregate results after formatting improvements.
- Tests: **14 passed**, including explicit/ambiguous dates, absent fields, duplicate/conflict and price-order checks, per-series gaps, units, tamper detection, raw-directory discovery, chunk validation, state audit before commodity filtering, scope/shorter-history selection, redaction and different-working-directory execution.
- `pip check`: passed. Python compilation of the data scripts: passed.
- Backend regression: temporary local Uvicorn instance returned HTTP 200 with exact `{"status":"ok","service":"agrisense-api"}` and expected localhost CORS; only that verification process was stopped afterward.
- `git diff -- backend frontend`: no changes. Bulk data, local samples/coverage, intermediate/processed output and actual environment files are ignored; compact reports and synthetic tests are eligible for review/commit.
- Earlier sandbox test attempts were blocked by Windows temporary-directory permissions. Approved runs outside that sandbox passed; this was not a dataset/test logic failure.

### Remaining limitations and next action

Day 2 code and profiling are complete. Full two-year unchanged-series coverage is a **data limitation**, not claimed complete. Use the documented shorter-history recommendation or obtain more compatible data/verify a valid label crosswalk. The raw duplicate/price anomalies are preserved for Day 3 review. Arrivals are unavailable. Exact Kaggle release/acquisition time and independent upstream reconciliation remain unverified.

Read [DATA_PROFILE.md](../reports/data/DATA_PROFILE.md), [DATA_SOURCES.md](DATA_SOURCES.md) and [DAY_02.md](DAY_02.md). No further download or Vercel action is needed to reproduce the present profile. The existing projects remain `agrisense-api` at https://agrisense-4lqq.vercel.app and `agrisense-web-v2` at https://agrisense-web-v2.vercel.app.

## Day 1 status

Day 1 implementation is complete. Local command-line and HTTP verification passed.
Browser interaction and visual verification remain manual because no browser is connected to this session.
This section records the Day 1 baseline; the completed Day 2 workflow is recorded above.

## Completed

- Next.js App Router frontend with TypeScript, Tailwind CSS, ESLint, responsive styling, and planned-feature labels.
- Browser-only health request with a five-second timeout, strict response validation, loading/success/error states, cleanup, and retry.
- Self-contained `backend/app.py` exports `app` and serves the required `GET /health` response.
- Environment-configured CORS for both local frontend origins. Backend `.env` resolves relative to `app.py`, with hosted environment settings taking priority.
- Local environment files and safe `.env.example` files for both services.
- Project-local Node.js 24 LTS and one designated Python environment at `.venv/`.
- Required future-day directories and `.gitkeep` placeholders; no future pipelines, models, database, or workflow implementation.
- Frontend dependency lockfile and pinned direct backend dependencies.
- README, Day 1 explanation, GitHub instructions, future two-project Vercel guide, and presentation notes with the supplied owner details.
- Git on `main`, preserving the existing initial commit and `origin` remote. The exact workspace was trusted in Git to resolve its Windows ownership error.

An additional ignored `venv/` directory was present when work resumed. It was preserved; all project commands use `.venv/` only.

## Installed versions used for verification

| Tool/package | Version |
| --- | --- |
| Windows PowerShell | 5.1 |
| Project-local Node.js | 24.21.0 LTS |
| Project-local npm | 11.19.0 |
| System Node.js (not selected for this project) | 26.2.0 |
| Git | 2.55.0.vfs.0.10 |
| Project Python | 3.13.10 |
| Other detected Python | 3.14.8 |
| Next.js / eslint-config-next | 16.3.8 |
| React / React DOM | 19.3.0 |
| TypeScript | 5.9.3 |
| Tailwind CSS / PostCSS plugin | 4.3.3 |
| ESLint | 9.39.5 |
| FastAPI | 0.142.2 |
| Uvicorn | 0.53.0 |
| python-dotenv | 1.2.4 |

`frontend/package-lock.json` records the exact npm dependency tree.
`backend/requirements.txt` pins the three direct Python packages needed today.

## Actual verification results

| Check | Result |
| --- | --- |
| `npm.cmd run lint` | PASS, zero warnings after fixing the PostCSS default export |
| `npm.cmd run typecheck` | PASS |
| `npm.cmd run build` | PASS; homepage statically prerendered, backend stopped throughout the successful build |
| `npm.cmd run start` | PASS; production homepage HTTP 200, expected project text, initial loading state, API address, and planned labels present |
| `npm.cmd run dev` | PASS; development homepage HTTP 200 |
| `python -m pip check` in `.venv` | PASS, no broken requirements |
| `GET http://127.0.0.1:8000/health` | PASS, HTTP 200 and exact `{"status":"ok","service":"agrisense-api"}` |
| `GET /docs` | PASS, HTTP 200 and Swagger UI HTML |
| `GET /openapi.json` | PASS, health route present |
| CORS: localhost and 127.0.0.1 frontend origins | PASS, exact matching `Access-Control-Allow-Origin` response header |
| CORS: unlisted origin | PASS, no allow-origin header |
| Import/configuration from root and `backend/` | PASS; environment override also checked |
| Git exclusions | PASS for `.env` files, `.venv`, `venv`, `.tools`, node_modules, build output, datasets, generated model files |
| Safe examples/lockfile/placeholders | Not ignored; eligible for the next commit |
| Sensitive/generated paths in Git's tracked file list | Actual `.env` files and dependency directories absent |
| `npm.cmd audit --omit=dev` | PASS, zero reported production vulnerabilities |
| Browser health/retry/timeout and responsive visual inspection | MANUAL CHECK REQUIRED; browser inventory was empty and opening the in-app browser returned unavailable |

The successful build required an approved run outside the command sandbox after Windows denied a build worker with `spawn EPERM`. This was an execution-environment restriction, not an application compile error. The earlier package-download/approval interruption was resolved during completion.

The backend log also recorded a Windows asyncio client-disconnect `WinError 10054` during the HTTP checks. All requested responses passed, and the API continued serving `/docs` and `/openapi.json`; no endpoint failure accompanied that disconnect.

Next.js generated `frontend/AGENTS.md`, `frontend/CLAUDE.md`, and updated `next-env.d.ts` during development startup. These are framework-generated project guidance/type files, not application features.

## Known dependency limitations

The full npm audit reports five related high-severity entries in the development-only chain
`eslint-config-next -> @next/eslint-plugin-next -> fast-glob -> micromatch -> braces`.
The registry's latest `braces` version is 3.0.3 and the audit includes it in the affected range.
There was no compatible patched release available during this check. Do not run `npm audit fix --force` blindly: its suggested change downgrades the Next.js lint configuration to a different major version.

ESLint 9.39.5 is deprecated upstream but is retained for compatibility with the current Next.js React/import/accessibility plugins. ESLint 10.12.0 was tested and failed those plugins; it is not in the final dependency tree. Revisit the lint toolchain when compatible upstream updates are available. These limitations do not prevent today's lint, build, or local health checks from passing.

## Day 1 handoff record (historical)

The `/docs` page now hides its visible `/openapi.json` link, as requested. The schema endpoint remains available for Swagger UI. Direct checks confirmed the custom docs HTML contains the hiding rule and the health/schema responses remain intact; browser visual confirmation is still manual.

1. Start the services with [README.md](../README.md). Verification servers were stopped after checks to leave ports 3000 and 8000 free.
2. Open the homepage and confirm **Backend connected**. Stop the backend, click **Retry connection**, confirm failure, then restart it and retry to confirm recovery. Inspect the browser Network panel for `/health`; inspect mobile and desktop layouts.
The obsolete initial GitHub and future-deployment walkthroughs were removed during Day 3; the working deployments and local runtime instructions remain in README.

## Next task

**Day 4: exploratory data analysis.** Use the canonical cleaned observations and inspect distributions, seasonal patterns and coverage within each exact series. See [Day 3](DAY_03.md) for cleaning rules and verification.

Roadmap: 1 setup; 2 real data; 3 cleaning; 4 exploration; 5 baselines; 6 features;
7 training; 8 evaluation; 9 database; 10 API; 11 dashboard; 12 selling calculator;
13 tests and refresh; 14 deployment and presentation.
