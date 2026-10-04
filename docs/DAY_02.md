# Day 2: Gujarat historical-data workflow

Project owner: **Krishkumar** | Roll No: **2401CS83** | **IIT Patna**

Repository: https://github.com/Krish290107/agrisense

**Status:** Day 2 import, profiling, source documentation and available verification are complete using the supplied real Kaggle CSVs. The state is Gujarat. The recommended scope is explicitly shorter than the original two-year target; data limitations are recorded rather than repaired by inventing observations.

## Files and responsibilities

| File/folder | Purpose |
| --- | --- |
| `requirements-data.txt` | pandas 3.0.6 for local tools; backend dependencies unchanged |
| `configs/data_sources.json` | Kaggle attribution/unit evidence, earlier official-source checks, aliases and explicit Gujarat scope policy |
| `scripts/market_data_common.py` | Strict string-preserving CSV chunks, hashing, parsing and metadata redaction |
| `scripts/import_market_data.py` | Import one file or directory, preserve original bytes, record provenance, skip duplicate content |
| `scripts/profile_market_data.py` | Audit input/Gujarat counts, profile the three commodities, report quality and separate-series coverage |
| `data/raw/2024.csv`, `2025.csv` | User-supplied originals, preserved and ignored by Git |
| `data/raw/historical/<sha256>/` | Unchanged copies and per-file provenance; ignored by Git |
| `data/interim/`, `data/processed/` | Placeholders for later days; no cleaned/training table written |
| `reports/data/DATA_PROFILE.md`, `data_profile.json` | Reproducible aggregate findings |
| `reports/data/recommended_scope.csv` | Small 15-row aggregate recommendation; no source price observations |
| `reports/data/local/` | Ignored complete coverage table, per-file profile and small original-row samples |
| `tests/test_market_data.py`, `tests/fixtures/` | Isolated, explicitly synthetic verification inputs |
| `docs/DATA_SOURCES.md`, `DATA_DICTIONARY.md` | Real provenance, observed schema, limitations and future feature rules |

The initial importer rejected any file inside `data/raw` and loaded a complete CSV in memory. It now accepts original files there, excludes managed bundle folders when discovering inputs, validates records in chunks, streams checksums/copies, and verifies the copy before publishing an immutable bundle. The profiler scans all rows but retains only the selected Gujarat commodities for detailed in-memory analysis. This supports the supplied 1.1 GB of CSVs without a full national dataframe.

## 1. Existing Python environment

```powershell
cd C:\Zekrui\agrisense
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-data.txt
```

If activation is blocked, use the existing environment executable directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
```

No new environment is needed. The tested runtime is Python 3.13.10, pandas 3.0.6. The data-tool dependency file is separate from `backend/requirements.txt` and is not needed on Vercel.

## 2. Reproduce the real import and profile

```powershell
cd C:\Zekrui\agrisense
.\.venv\Scripts\python.exe scripts\import_market_data.py data\raw --source kaggle_daily_india --kind historical --date-format "%Y-%m-%d"
.\.venv\Scripts\python.exe scripts\profile_market_data.py --state Gujarat --commodities Onion Potato Tomato
```

Both supplied files have already been imported. Repeating the first command reports `duplicate_skipped` for identical content. Original filenames and bytes remain unchanged; new imports go into full-SHA-256-named bundles. The importer skips `data/raw/historical/` and `data/raw/snapshots/` while discovering originals, so running it on `data/raw` does not recursively reimport its copies.

For one additional genuine file, replace `data\raw` with its CSV path. For a separate directory, use its path; CSV discovery is recursive. Relative paths resolve from the repository root independently of the terminal's working directory. Future files need their own true source metadata and date format; do not mislabel an unrelated download as this Kaggle dataset.

Each bundle's `provenance.json` records source URL/publisher, original filename, import UTC timestamp, acquisition timestamp if known, SHA-256, bytes, row count, original headers, actual parsed date coverage, encoding, delimiter, mapping, units, retrieval parameters and license/attribution status. The original acquisition time and Kaggle release version for these user-supplied files are unknown.

Advanced options remain available through `--help`: `--source-url`, `--publisher`, `--acquired-at`, `--price-unit`, `--quantity-unit`, `--license-status`, `--column-map`, `--encoding`, `--delimiter`, and redacted `--parameter name=value`. Only supply confirmed metadata. Without a date format, only ISO dates are accepted; ambiguous slash dates are counted as failures. Raw bundles are not edited to resolve parsing or quality problems.

A current data.gov.in export uses `--source data_gov_in --kind snapshots`. Snapshot reports use `--kind snapshots` and are kept separate from historical reports. No fetcher is added because the earlier official API probes did not verify live response behavior. No key is needed to process the supplied local files.

## 3. Actual findings

- **All-state input:** 11,363,982 rows. `2024.csv`: 5,544,500 rows, 366 dates, 2024-01-01 to 2024-12-31. `2025.csv`: 5,819,482 rows, 342 dates, 2025-01-01 to 2025-12-30. Original dates all parse under `%Y-%m-%d`.
- **Gujarat, all commodities:** 523,868 rows, 707 distinct observation dates, 2024-01-01 to 2025-12-29.
- **Gujarat selected commodities:** 39,634 rows: Onion 12,667; Potato 13,002; Tomato 13,965. There are 229 distinct state/district/market/commodity/variety/grade series and 704 pooled dates across this selected subset.
- **Schema:** 11 columns, including variety and grade; no arrivals or unit columns. `Commodity_Code` is preserved as an extra source identifier. INR/quintal is supported by the Kaggle publisher's description, not inferred from prices.
- **Selected-subset quality:** zero date/numeric parse failures; one exact duplicate beyond the first and one repeated business key; zero conflicting keys; nonpositive minimum price in one row and nonpositive maximum price in two rows; two price-order violations. Those flags affect three distinct series. Original observations remain unchanged.

The report labels all-state inventory, state-wide audit and filtered quality metrics separately. Counts from a union of markets do not prove that any individual market reported every day.

## 4. Recommended manageable scope

The original screen required 700 days of same-series span. **Zero series passes that screen; the longest span is 675 days.** The report retains that result. It separately offers a configured 600-day minimum for a provisional shorter-history scope, retaining every other date/price/unit/gap check. This is roughly 22 months for the selected series, not a completed two-year history requirement.

The result selects 15 market-commodity combinations, five per commodity, across eight reported markets. Each keeps one explicit variety and grade; all selected grades are FAQ. See [the generated recommendation table](../reports/data/recommended_scope.csv) for exact identifiers, date endpoints, observed-day counts, coverage and gaps. The selected series have 516-633 observation days, approximately 76.4%-94.1% calendar coverage, and longest internal gaps of 3-18 days.

| Market | Recommended commodities |
| --- | --- |
| Dahod (Veg. Market) | Onion, Potato, Tomato |
| Bilimora | Onion, Potato, Tomato |
| Kapadvanj | Onion, Potato, Tomato |
| Nadiyad (Piplag) | Onion, Tomato |
| Navsari | Tomato |
| Ankleshwar | Potato |
| Nadiad | Potato |
| Morbi | Onion |

The original labels matter. Later data includes APMC-suffixed market names, for example `Bilimora APMC` and `Dahod (Veg. Market) APMC`, sometimes with different variety/grade values. They are not automatically equated with the earlier names. Day 3 may investigate a verified market-name crosswalk and grade definitions, but joining them now would overstate continuous coverage. The reported variety `Other` is retained as a source category, not treated as proof of uniform quality.

Screening choices are in `configs/data_sources.json`: 365 positive modal observation days, 50% minimum calendar coverage, 45-day maximum internal gap, known variety/grade and consistent price units, with price/date/conflicting-key flags excluded. The explicit shorter-history fallback changes only the span threshold. These choices are not proof of forecasting accuracy. No data is imputed or grades merged.

## 5. Read the reports

1. `reports/data/DATA_PROFILE.md`: human-readable inventory, commodity counts, quality findings, grade coverage and recommendation.
2. `reports/data/data_profile.json`: machine-readable aggregate evidence, source hashes, scope filters and all thresholds. Compact previews are capped; selected combinations are fully listed.
3. `reports/data/recommended_scope.csv`: only the small recommended-series aggregate table; safe to review/commit.
4. `reports/data/local/series_coverage.csv`: all 229 selected-subset series. State and district are included. Inspect unique dates, span, missing calendar days, longest gaps and quality flags.
5. `reports/data/local/file_profiles.json`: every input file's filtered columns/missingness/mappings and quality counts.
6. `reports/data/local/samples.json`: up to three unchanged sample rows per file, local-only and ignored by Git.

Rerunning profiling replaces derived reports, never originals. Defaults now use Gujarat and Onion/Potato/Tomato. `--all-records` explicitly disables filtering and can require substantial memory; it is unnecessary for the project scope. Missing dates are not zero prices; calendar gaps can be closures or non-reporting. Missing varieties/grades stay separate unknown buckets.

## 6. Verification and Git handoff

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_market_data.py" -v
.\.venv\Scripts\python.exe -m pip check
git diff --check
git status --short
git check-ignore -v data/raw/2024.csv data/raw/2025.csv data/interim/example.csv data/processed/example.csv reports/data/local/samples.json backend/.env frontend/.env.local
```

The offline tests use only clearly labeled synthetic rows in temporary folders. They verify explicit dates, missing optional fields, duplicates/conflicts, price checks, gaps, units, provenance integrity, raw-directory discovery, chunk boundaries, filtering, shorter-history labeling, redaction and working-directory independence. Synthetic fixture statistics never enter the real-data report. See [PROGRESS.md](PROGRESS.md) for actual results.

Bulk raw/intermediate/processed data, local samples, environments and credentials stay ignored. Compact aggregate reports retain the reproducible findings.

## Deployment and next step

No Vercel action is needed. Frontend/backend code, dependencies and deployment configuration are preserved:

- Backend project **agrisense-api**: https://agrisense-4lqq.vercel.app
- Frontend project **agrisense-web-v2**: https://agrisense-web-v2.vercel.app

Day 3: review the duplicate and price flags, source-label changes and missing dates, then document cleaning decisions. If a full two-year same-series window is mandatory, obtain more compatible observations or verify a valid source identity crosswalk. Do not fabricate missing data. No production cleaning, model, database or forecasting UI has been implemented today.
