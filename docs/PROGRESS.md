# AgriSense progress

**Project owner:** Krishkumar

**Roll No:** 2401CS83

**Institution:** IIT Patna

**GitHub repository:** https://github.com/Krish290107/agrisense

**Updated:** October 6, 2026 (Asia/Calcutta)

## Day 13 status: reliability and automation complete locally

91 Python tests (also in a clean source-only copy), 11 frontend tests, typecheck, lint and build pass. Added fixture-based cross-language HTTP smoke verification and one minimal CI workflow. Canonical temporary rebuild/import twice preserves 39,630 observations, 229 series and 9 active policies; 87 protected hashes remain unchanged. Configuration validation and regressions added. Hosted CI execution and browser visual checks remain unperformed. See [DAY_13.md](DAY_13.md).

## Day 12 status: implemented and programmatically verified

Added price signals, read-only active-market comparison, quantity/gross proceeds calculations and deterministic summaries to the existing dashboard. Exact variety/grade comparisons are preferred; broader comparisons carry a warning. No downloads, dependencies, policy/schema changes or comparison persistence. Details and real-data results: [DAY_12.md](DAY_12.md).

All 89 Python tests and 10 frontend tests pass, alongside typecheck, lint and production build. The real HTTP endpoint and frontend client verified Dahod Potato and both comparison scopes. Browser visual verification remains unperformed.

## Day 11 status: dashboard implemented — visual verification pending

Replaced the landing-page hero, milestone and planned-feature sections with a real forecast dashboard. API-driven commodity/market selectors, compact health status, next-observation generation, modal-price chart, recent observations and saved forecasts are connected. No forecast is generated on page load. Exact identities, history cutoffs, fallback and null unavailable results are preserved. The frontend adds no forecast calculations or dependencies.

Typecheck, lint and production build pass; seven frontend contract/client tests and all 85 Python regression tests pass. The real frontend API module verified nine supported series, 30-record histories for Dahod Onion/Potato and predictions displayed as ₹1,442.86/₹1,428.57. Two real forecast rows were saved and reused on repeat requests. Historical data, policy, backend code and CORS remain unchanged during Day 11.

Desktop/tablet/mobile CSS and accessibility states are implemented, but browser interaction and visual review could not run: the browser connector had no available browsers and the Windows helper's native pipe was unavailable. Do not treat this as a visual pass. See [Day 11 verification](DAY_11.md).

## Day 10 status: complete — next-observation forecast service and API

Added HTTP-independent baseline forecasting and typed `/api/v1/forecast` routes for supported-series discovery, recent observations, generation and stored history. All nine active policies remain: seven naive and two rolling mean 7. Results identify next-observation semantics, decimal-string prices, method/fallback, used-history cutoff and historical benchmark context. Missing history returns null; unsupported series cannot acquire an arbitrary forecast method. No production ML or frontend changes.

Successful forecasts persist with a deterministic history/policy/request fingerprint; concurrent equivalent requests reuse one saved row. Added optional existing-file/read-only connection modes and immediate transactions to the repository without changing schema or default importer behavior. Health remains unchanged; configured CORS origins remain, with POST added. Missing/uninitialized storage fails clearly instead of creating an empty database. No new dependencies or downloads.

**14 focused and 71 regression tests passed (85 total).** Read-only calculations verified all nine real candidates; GET smoke checks verified discovery/history/stored history, health and OpenAPI. The real database stays byte-identical with zero forecast records; persistence tests use isolated databases. Ninety protected historical paths remain unchanged. Day 9 reports and original implementation hashes remain historical records; the repository's small Day 10 extension is documented separately. See [Day 10](DAY_10.md) and the [API report](../reports/data/FORECAST_API_REPORT.md).

## Day 9 status: complete — local database and persistence

Added standard-library SQLite schema version 1, a small reusable repository and one transactional import command. The ignored local `data/agrisense.db` stores **39,630 observations, 229 exact historical series, nine active policy entries, one experimental model bundle, 405 concise evaluation metrics and seven ingestion records**. Coverage is **2024-01-01 through 2025-12-29**. No generated forecast rows, new dependencies or external downloads.

All source price text and provenance roundtrip exactly; decimal CHECK functions reject nonfinite/nonpositive prices and invalid ordering without floating-point conversion. Six-field identity and series/date uniqueness, foreign keys, policy requirements, date formats and explicit null forecast failure states are enforced. Policy import preserves seven naive and two rolling-mean-7 series. ML remains experimental. Exact lookup, latest observation, chronological latest-N/as-of history and policy reload pass for all nine candidates.

Ten focused database tests and 61 regression tests pass using only temporary/in-memory databases. Repeated real imports preserve row counts and summaries, leave existing forecast rows intact and produce no duplicate observations. The finalized full rerun preserves deterministic reports; protected historical hashes remain unchanged. See [Day 9](DAY_09.md) and the [database report](../reports/data/DATABASE_REPORT.md). No API endpoints, frontend changes, retraining, policy changes or deployment were introduced.

## Day 8 status: complete — robustness evaluation and frozen policy

Reconstructed all 126 baseline metric rows and 540 ML predictions within numeric tolerance. A nonwinning Bilimora Onion validation rank tie changes order after CSV roundtrip; original ranks and all historical artifacts remain intact. Evaluated three chronological 20-observation blocks per exact series (27 origins, 540 targets), with all seven baseline methods, original fixed ML and block-refitted frozen ML configurations. No new dependencies, tuning, API or frontend changes.

Retained baseline MAE is **119.55 INR/quintal**, against **135.86** for block-refitted ML; baseline wins all nine series and all three pooled blocks. ML wins three individual series-block comparisons and reduces shock/long-gap error, so superiority is not universal. Tomato remains the hardest commodity. The 46 shock observations account for 31.2% of baseline absolute error. Long-gap estimates have only 17 observations.

The reloadable `configs/forecast_policy.json` retains seven naive series and two rolling-mean-7 series. Invalid/missing trailing history falls back to the last valid observation; no valid history yields explicit insufficient_history with null prediction. Unknown identities are rejected explicitly. All 540 historical policy predictions reproduce after reload. ML remains experimental, preserved for research. No uncertainty bands are claimed without an independent calibration period.

Nine focused tests and 52 prior regression tests pass. Eight figures and new evaluation tables/report are in `reports/figures/evaluation/` and `reports/data/`. Full real-data rerun and historical hash checks are described in [Day 8](DAY_08.md). Existing test dates were already examined: the robustness blocks are descriptive evidence, not fresh independent validation.

## Day 7 status: complete — ML validation and honest baseline comparison

Evaluated five scikit-learn families with seven modest configurations per exact series: Ridge alpha 1/10, Random Forest (100 trees, depth 6, leaf 3/8), Extra Trees (100 trees, depth 6, leaf 3), Gradient Boosting (100 trees, learning rate .05, depth 2, leaf 8), and HistGradientBoosting (100 iterations, .05 learning rate, 15 leaves, minimum leaf 15, L2=1, no early stopping). Scikit-learn 1.9.1 was installed in the existing environment and `scikit-learn>=1.6` was added to requirements-data.txt; no external dataset or manual download was needed.

All 27 features were inspected; the 21 historical-only features were used. Six target-date features were excluded to preserve Day 5's unknown-next-report-date information contract. Exact-series models avoid cross-market temporal leakage: nominal validation/test periods overlap across markets, making a single all-row pooled fit/selection unsafe without a different synchronized evaluation design. All existing splits remain unchanged: **4,011 train / 540 validation / 540 test**. Identity encoding and Ridge scaling fit on each allowed training region only.

Validation-only selection yields Ridge alpha 10 for four series, Ridge alpha 1 for one, Random Forest leaf 8 for two, Random Forest leaf 3 for one, and Extra Trees for one. Selected macro validation MAE is **147.59**, mean per-series RMSE 214.75 INR/quintal. Selection was repeated deterministically, frozen before test, then each selected pipeline was refitted on its own train+validation history (4,551 total rows). All fit dates precede the corresponding series' test start; weights stay fixed while historical inputs update one observed step at a time.

**ML did not beat the simple baselines.** ML macro test MAE **136.20** versus Day 5 **119.55** gives improvement **−16.65 INR/quintal (−13.93%)**. ML wins **0/9**, baseline wins **9/9**, ties **0/9**. Mean per-series RMSE is 192.70; pooled RMSE is 225.51 and pooled sMAPE 8.69%. Commodity MAE (ML vs baseline): Onion 101.72 vs 80.32; Potato 68.49 vs 51.94; Tomato 238.38 vs 226.39. The worst absolute deterioration is Bilimora Potato (+38.63); the smallest is Dahod Potato (+3.75). Navsari Tomato's largest shock miss falls from 2,000 to 1,494.91, but its overall MAE still worsens. No test-driven retuning or switching to baselines was performed.

The [ML report](../reports/data/ML_MODEL_REPORT.md), [comparison](../reports/data/ml_baseline_comparison.csv), frozen selection, validation scores and model metadata record the evidence. Nine figures were visually inspected. The saved local `ml/models/agrisense_price_model.joblib` bundle includes preprocessing and nine exact-series models; reload reproduces all 540 test predictions. Top normalized explanatory features: modal lag 1, rolling median 3, rolling mean 3, rolling mean 7, modal lag 2. These model-specific importance measures are not causal feature rankings or test-based selections.

All **seven Day 7 tests and 45 regression tests pass**. Independent checks verify exact test identities/dates, metrics, baseline joins, validation-only selections, fit-only scaler statistics/categories, finite predictions and reload equality. Re-running from another directory verifies byte-identical stored artifacts without retraining/rescoring. Dependencies, compilation, report links and ignore protections pass. Every prior report, figure, local audit, raw source hash, cleaned dataset and feature dataset remains unchanged; no files were removed. Existing ignored paths cover the model and prediction rows.

The historical test had already been examined in earlier days, so it is not a pristine project-wide holdout despite Day 7's isolated selection. Cohort selection, limited/stale history and unknown publication timing also limit generalization. Keep these negative results unchanged; Day 8 should study robustness and validation-supported choices without presenting repeated test optimization as independent evidence.

## Day 6 status: complete — causal historical features

Processed all nine exact candidate series: **5,154 observations → 5,091 usable rows**, removing only the first seven training rows per series (63 total). Output regions contain **4,011 train / 540 validation / 540 test rows**. All 1,080 Day 5 validation/test identities, dates and target values match the immutable baseline predictions exactly. The [feature report](../reports/data/FEATURE_ENGINEERING_REPORT.md), [metadata](../reports/data/feature_metadata.json) and [summary](../reports/data/feature_summary.json) document the local `data/processed/forecast_features.csv`.

The 27 features cover observation lags, shifted rolling mean/median, historical volatility/range, previous changes, expanding statistics, prior min/max/spread, completed historical gaps and calendar/timing fields. No same-row target/min/max enters the explicit feature list. Twenty-one features require only historical records; six additionally assume the target date is known. That date-known assumption is new relative to Day 5's unknown next reporting date, so strict benchmark-information comparisons should use the historical-only list. Full-feature results must disclose the extra date information.

All **nine Day 6 tests and 36 regression tests pass**. Tests cover exact formulas, irregular dates, separated markets/varieties/grades, missing warm-up history, fixed splits, deterministic ordering and current/future-price mutations. Independent prefix reconstruction verifies every feature across all 5,091 retained rows. This check exposed incremental rolling-variance residuals on constant windows; short-window sample standard deviation now recomputes directly, correctly returning genuine zero variance without filling unavailable values. Retained features contain no missing/infinite values.

The real pipeline ran twice; all five artifacts were byte-identical, including a run from another working directory. Original raw hashes still match provenance, and canonical cleaned data plus every existing Day 2–5 report, figure and local audit are unchanged. No dependencies were added, no models or correlations were fitted, no missing observations were generated, and no files were removed. Feature definitions were not optimized against test scores. Supervised ML loses early warm-up rows while preserving all baseline evaluation targets; later modeling must keep training/preprocessing/tuning chronological.

## Day 5 status: complete — statistical baselines and chronological backtesting

Evaluated all nine exact Day 4 candidates with seven univariate baselines: naive, historical mean/median, rolling means over 3/5/7 observations, and rolling median over 5 observations. Each series retains 406–513 initial observations, followed by 60 validation and 60 test records. Expanding-history evaluation produces **7,560 forecast comparisons**: 3,780 validation and 3,780 test, covering 1,080 distinct series/date targets. Forecast horizon is the next observed record, with no calendar filling.

Validation MAE selects naive for seven candidates and the seven-observation rolling mean for Dahod Onion and Potato; selections are frozen before test. Selected-model mean test MAE is **119.55 INR/quintal**, median 85.00. The all-naive reference mean test MAE is 126.20. Retrospective test rankings remain separately labeled; the validation-selected Dahod models were not the test-period winners. [Best baselines](../reports/data/best_baselines.csv), [all metrics](../reports/data/baseline_metrics.csv) and [report](../reports/data/BASELINE_FORECAST_REPORT.md) retain exact identities and scores.

Selected-model test MAE by commodity is Onion 80.32, Potato 51.94, Tomato 226.39 INR/quintal. The largest miss is 2,000 INR/quintal for Navsari Tomato on 2025-08-25 after a 44.4% observed price drop, despite a one-day elapsed gap. Longer-gap pooled MAE is 153.84 over 93 observations versus 112.42 over 447 consecutive-day observations; differing commodities/markets and sparse gap buckets prevent a causal interpretation. No difficult observations are removed.

Eight figures in `reports/figures/baselines/` were visually inspected. Prediction rows stay in ignored `reports/data/local/baseline_predictions.csv`; compact reports include fixed splits, metrics, error examples and input/code/output hashes. All **eight Day 5 tests and 28 data regression tests pass**. Independent verification reconstructs all 7,560 predictions using only past modal prices and checks dates, phase boundaries, metrics and validation-only selection. A rerun from another working directory produced byte-identical results across all 17 artifacts. Original CSV hashes match provenance; canonical cleaned data and Day 3/4 artifacts are unchanged. Compilation, dependency consistency, links and ignore protections pass; frontend/backend/configuration/dependencies are unchanged. No files were removed and no packages were added.

The pipeline prevents silent benchmark replacement when inputs, implementation, policy or software versions change. Historical cohort selection used full-history Day 4 coverage; this limits generalization even though individual forecasts are leakage-safe. Seasonal baselines are omitted because exact series have fewer than two full annual cycles and irregular dates. Future models must use comparable past-only data and fixed boundaries, with validation tuning and explicit limits on repeated test-set use.

## Day 4 status: complete — EDA and historical baseline readiness

Analyzed all **39,630 rows, 229 series, 81 district-market combinations, 22 districts**, covering 2024-01-01 through 2025-12-29. Ten figures and deterministic aggregate tables accompany the [EDA report](../reports/data/EDA_REPORT.md). Median modal prices are Onion 1,607.5, Potato 1,600 and Tomato 2,000 INR/quintal; pooled Tomato variability is highest. These are descriptive comparisons, not joined forecasting targets.

Readiness is **53 eligible, 30 limited, 146 insufficient**. The median series has 14 observations; the largest internal missing-calendar gap is 425 days. A transparent shorter-history screen uses 365 observations, 600-day span, 50% density, maximum 45-day internal gap and recency within 60 days of dataset end. No long-history series passes a 30-day recency screen. This supports historical evaluation only, not current-price forecasting.

Nine exact candidates, three per commodity, are listed in [forecast_candidates.csv](../reports/data/forecast_candidates.csv): Dahod (Veg. Market) and Bilimora for all three commodities, Kapadvanj for Onion/Potato, and Navsari for Tomato. Variety and grade are explicit in each row. A conservative within-series outer-IQR screen flags 88 observations across 19 series without deleting them; 123 short/constant series are not screened.

Reproduce with `.\.venv\Scripts\python.exe scripts/run_eda.py`. Existing pandas/NumPy/Matplotlib installations were reused; no downloads were needed. Redundant comments were removed or shortened while preserving provenance, integrity and generated tooling explanations. No additional files were safe/necessary to delete; existing ignore rules already protect local outlier audits. No features, splits, models, API/UI behavior or deployment changes were introduced.

Verification: all five Day 4 tests and 23 Day 2/3 regression tests pass. Two final real-data runs produce byte-identical results across all 19 artifacts (nine tables/reports including the local audit, plus ten PNGs). Source CSV hashes still match provenance; the canonical cleaned CSV and Day 2/3 artifacts are unchanged. Figures were visually inspected, with gap/history counts shown as explicit categories and boxplot whiskers distinguished from the audit's outlier rule. Independent checks confirm row conservation, all 229 identities, nine eligible candidates and outlier accounting. Frontend type checking, backend import/health/schema/docs smoke checks, dependency consistency, compilation, documentation links and Git ignore/whitespace checks pass. Existing tracked Python files retain identical executable ASTs after comment cleanup.

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

**Day 14: final release polish, deployment verification and complete README usage guide**, including outstanding browser visual checks and observing hosted CI results.

Roadmap: 1 setup; 2 real data; 3 cleaning; 4 exploration; 5 baselines; 6 features;
7 training; 8 evaluation; 9 database; 10 API; 11 dashboard; 12 selling calculator;
13 tests and refresh; 14 deployment and presentation.
