# AgriSense data profile

Status: **profiled**
Input kind: **historical**
Generated UTC: 2026-10-04T17:35:29.020152Z

Project owner: Krishkumar | Roll No: 2401CS83 | IIT Patna
Repository: https://github.com/Krish290107/agrisense

## Input inventory and project filter

All-state input rows: 11,363,982. Selected project rows: 39,634.
State filter: Gujarat; commodity filter: Onion, Potato, Tomato.
State-wide audit before commodity filtering: 523,868 rows, 2024-01-01 to 2025-12-29, 707 distinct dates.

| File | All-state rows | Actual first date | Actual last date | Distinct dates |
| --- | ---: | --- | --- | ---: |
| 2025.csv | 5,819,482 | 2025-01-01 | 2025-12-30 | 342 |
| 2024.csv | 5,544,500 | 2024-01-01 | 2024-12-31 | 366 |

| Commodity in selected state | Rows | First date | Last date | Observation dates | Markets (district + market) |
| --- | ---: | --- | --- | ---: | ---: |
| Onion | 12,667 | 2024-01-01 | 2025-12-29 | 694 | 57 |
| Potato | 13,002 | 2024-01-01 | 2025-12-29 | 699 | 50 |
| Tomato | 13,965 | 2024-01-01 | 2025-12-29 | 702 | 61 |

## Quality of filtered project records

Files: 2; rows: 39634; series: 229.
Actual parsed date range: 2024-01-01 to 2025-12-29 (704 distinct dates).

| Check | Count |
| --- | ---: |
| Missing dates | 0 |
| Date parse failures | 0 |
| Exact duplicate rows beyond first | 1 |
| Repeated candidate keys | 1 |
| Conflicting candidate keys | 0 |
| Price order violations | 2 |
| Price order uncheckable rows | 0 |

Nonpositive prices by column: {'min_price': 1, 'modal_price': 0, 'max_price': 2}.
Numeric parsing failures: {'min_price': 0, 'modal_price': 0, 'max_price': 0, 'arrivals': 0}.
Price units: INR/quintal; missing price-unit rows: 0. Source declarations are recorded in input provenance; absent quantity fields are not invented.

See data_profile.json for per-column missingness, numeric failures, nonpositive prices, dimensions, units, and compact series coverage.

## Grade coverage (pooled dates, not joined series)

| Commodity | Grade | Rows | First | Last | Distinct dates |
| --- | --- | ---: | --- | --- | ---: |
| Onion | FAQ | 12086 | 2024-01-01 | 2025-12-29 | 690 |
| Onion | Grade A | 18 | 2025-11-29 | 2025-12-29 | 16 |
| Onion | Grade B | 4 | 2025-12-03 | 2025-12-26 | 4 |
| Onion | Local | 29 | 2025-12-03 | 2025-12-29 | 18 |
| Onion | Non-FAQ | 530 | 2025-01-18 | 2025-12-27 | 271 |
| Potato | FAQ | 11824 | 2024-01-01 | 2025-12-29 | 697 |
| Potato | Grade A | 16 | 2025-12-05 | 2025-12-29 | 15 |
| Potato | Grade B | 5 | 2025-12-20 | 2025-12-27 | 5 |
| Potato | Local | 41 | 2025-12-04 | 2025-12-29 | 22 |
| Potato | Medium | 6 | 2025-12-04 | 2025-12-27 | 6 |
| Potato | Non-FAQ | 1110 | 2025-01-17 | 2025-12-27 | 276 |
| Tomato | FAQ | 12533 | 2024-01-01 | 2025-12-29 | 698 |
| Tomato | Grade A | 8 | 2025-12-04 | 2025-12-27 | 7 |
| Tomato | Grade B | 1 | 2025-12-26 | 2025-12-26 | 1 |
| Tomato | Local | 79 | 2025-12-03 | 2025-12-29 | 27 |
| Tomato | Medium | 7 | 2025-12-05 | 2025-12-26 | 7 |
| Tomato | Non-FAQ | 1337 | 2025-01-17 | 2025-11-06 | 284 |

These grade totals pool several markets/varieties for inspection only. They are not a forecasting series.

## Scope recommendation

Scope status: **provisional_shorter_history**.
No series meets the original 700-day screen. This explicitly shorter-history option uses 600 days minimum; it does not fulfill the two-year target. Keep each listed variety/grade separate; do not join FAQ and Non-FAQ. The project state remains Gujarat. All other quality, unit, observation-count and gap screens still apply.

Candidate state: Gujarat.
Candidate commodities: Tomato, Potato, Onion.
Selected combinations: 15; their exact varieties, grades, counts, gaps and units appear in the JSON recommendation.

| District | Market | Commodity | Variety | Grade | First | Last | Days observed | Coverage | Longest gap |
| --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: |
| Dahod | Dahod (Veg. Market) | Tomato | Tomato | FAQ | 2024-01-01 | 2025-11-03 | 633 | 94.1% | 3 |
| Dahod | Dahod (Veg. Market) | Potato | Potato | FAQ | 2024-01-01 | 2025-11-03 | 627 | 93.2% | 3 |
| Dahod | Dahod (Veg. Market) | Onion | Onion | FAQ | 2024-01-01 | 2025-11-04 | 612 | 90.8% | 4 |
| Navsari | Navsari | Tomato | Other | FAQ | 2024-01-03 | 2025-11-05 | 559 | 83.1% | 7 |
| Navsari | Bilimora | Potato | Other | FAQ | 2024-01-11 | 2025-11-05 | 547 | 82.3% | 18 |
| Navsari | Bilimora | Onion | Nasik | FAQ | 2024-01-11 | 2025-11-05 | 552 | 83.0% | 18 |
| Navsari | Bilimora | Tomato | Other | FAQ | 2024-01-11 | 2025-11-05 | 558 | 83.9% | 18 |
| Kheda | Kapadvanj | Potato | Other | FAQ | 2024-01-04 | 2025-11-04 | 540 | 80.5% | 12 |
| Kheda | Kapadvanj | Onion | Other | FAQ | 2024-01-03 | 2025-11-04 | 526 | 78.3% | 9 |
| Kheda | Kapadvanj | Tomato | Other | FAQ | 2024-01-03 | 2025-11-03 | 540 | 80.5% | 8 |
| Bharuch | Ankleshwar | Potato | Potato | FAQ | 2024-01-02 | 2025-11-03 | 529 | 78.7% | 11 |
| Kheda | Nadiyad (Piplag) | Onion | Onion | FAQ | 2024-01-02 | 2025-11-05 | 518 | 76.9% | 8 |
| Kheda | Nadiyad (Piplag) | Tomato | Tomato | FAQ | 2024-01-02 | 2025-11-05 | 526 | 78.0% | 8 |
| Kheda | Nadiad | Potato | Other | FAQ | 2024-01-02 | 2025-11-05 | 528 | 78.3% | 7 |
| Morbi | Morbi | Onion | Onion | FAQ | 2024-01-01 | 2025-11-05 | 516 | 76.4% | 11 |

Full two-year, same-series coverage remains unmet. Any shorter-history recommendation is provisional for later cleaning and validation, not permission to merge grades or fill missing prices.

## Read alongside this report

- `data_profile.json`: small aggregate report; previews are capped at 20 files/series.
- `local/series_coverage.csv`: every identifiable series, its observation days, span, gaps and quality flags (ignored by Git).
- `local/file_profiles.json`: every file's columns, mappings and quality counts (ignored by Git).
- `local/samples.json`: at most three original rows per file, for local inspection only (ignored by Git).

Missing variety/grade stays unknown. Incomplete state/district/market/commodity rows are reported separately. Missing dates are never zero prices; gaps may reflect closures or non-reporting.

These tools inspect data; they do not clean, impute, deduplicate, merge varieties, train, or establish forecasting accuracy.
