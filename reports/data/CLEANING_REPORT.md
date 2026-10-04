# Day 3 cleaning report

Krishkumar | 2401CS83 | IIT Patna

Repository: https://github.com/Krish290107/agrisense

Scanned 11,363,982 source rows; selected 39,634 Gujarat Onion/Potato/Tomato rows. Retained **39,630 observations in 229 separate series**.

Removed 4 rows: 3 quarantined, 1 exact duplicate copies and 0 equivalent key copies. Invalid price rows: 3; conflicting keys: 0. Issue counts may overlap; see cleaning_summary.json for complete accounting.

Cleaned dates: 2024-01-01 through 2025-12-29.

Canonical CSV: `data/processed/market_prices_clean.csv`. Local audit: `reports/data/local/rejected_rows.csv`, including original field values, source hash, CSV record number and all rejection reasons. Valid price text is retained without floating-point rounding. Unit INR/quintal comes from imported source provenance.

Whitespace is normalized; spelling, case, markets, districts, varieties and FAQ/Non-FAQ remain distinct. No missing dates or prices are filled. Source files are hash-verified and never written. All valid scoped observations are retained, not only the provisional Day 2 recommendation.

Cleaning does not establish forecasting eligibility: short/sparse series, unverified label equivalence, absent arrivals and incomplete two-year same-series history remain limitations. The Day 2 profile remains an unchanged raw-data baseline. No features or models are generated.
