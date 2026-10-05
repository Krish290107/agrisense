# Day 6: historical time-series feature engineering

Krishkumar | 2401CS83 | IIT Patna

Repository: https://github.com/Krish290107/agrisense

## Dataset and split preservation

9 exact series; 5,154 source observations produce 5,091 ML rows with 27 numeric features. Removed 63 early training rows only (seven per series). Train/validation/test counts: 4,011 / 540 / 540. All Day 5 validation/test identities, dates and target prices are preserved exactly.

| Series (Gujarat) | Source | Warm-up | Train | Validation | Test |
| --- | --- | --- | --- | --- | --- |
| Dahod / Dahod (Veg. Market) / Onion / Onion / FAQ | 612 | 7 | 485 | 60 | 60 |
| Dahod / Dahod (Veg. Market) / Potato / Potato / FAQ | 627 | 7 | 500 | 60 | 60 |
| Dahod / Dahod (Veg. Market) / Tomato / Tomato / FAQ | 633 | 7 | 506 | 60 | 60 |
| Kheda / Kapadvanj / Onion / Other / FAQ | 526 | 7 | 399 | 60 | 60 |
| Kheda / Kapadvanj / Potato / Other / FAQ | 540 | 7 | 413 | 60 | 60 |
| Navsari / Bilimora / Onion / Nasik / FAQ | 552 | 7 | 425 | 60 | 60 |
| Navsari / Bilimora / Potato / Other / FAQ | 547 | 7 | 420 | 60 | 60 |
| Navsari / Bilimora / Tomato / Other / FAQ | 558 | 7 | 431 | 60 | 60 |
| Navsari / Navsari / Tomato / Other / FAQ | 559 | 7 | 432 | 60 | 60 |

Source data, candidate readiness and the fixed Day 5 benchmark are hash-checked, never rewritten. The canonical output is `data/processed/forecast_features.csv`, sorted by six-field identity and date. `split` retains the Day 5 regions; `modal_price` is the output target, not an input feature. Use the explicit lists in [feature_metadata.json](feature_metadata.json), never all numeric columns by default. Identity categories stay unencoded. Same-row min_price/max_price are absent.

## Definitions and availability

| Family | Features |
| --- | --- |
| lag | modal_price_lag_1, modal_price_lag_2, modal_price_lag_3, modal_price_lag_5, modal_price_lag_7 |
| rolling | rolling_mean_3, rolling_median_3, rolling_mean_7, rolling_median_7 |
| volatility | rolling_std_3, rolling_std_7, rolling_range_7 |
| change | previous_price_change, previous_percentage_change |
| expanding | expanding_mean, expanding_median, expanding_std |
| historical_spread | min_price_lag_1, max_price_lag_1, previous_price_spread |
| timing | days_since_previous_observation, recent_mean_gap_3 |
| calendar | month, quarter, day_of_year, month_sin, month_cos |

Lags count prior actual observations: lag_7 need not mean seven calendar days. Rolling means, medians, sample standard deviations (ddof=1) and ranges operate on shift(1) history, requiring complete windows. Expanding statistics use all strictly earlier observations. Signed price change is price[t-1] minus price[t-2]; percentage change is 100 times their ratio minus one. Historical min/max/spread use t-1 only. Constant-history volatility may legitimately be zero; unavailable volatility is never zero-filled.

No missing calendar rows, interpolated prices or imputed feature history are created. All excluded rows are the expected initial seven observations of each series. Missing counts before and after warm-up removal are recorded in feature_summary.json; retained features have no missing or infinite values. The largest finite lookback is seven observations; expanding features require the entire available prefix. Historical mean gap uses the last three completed intervals (four prior observations), excluding the target interval.

## Target-date information contract

The requested Day 6 design assumes the prediction date is known before predicting its price. Six conditional features use that date: days_since_previous_observation, month, quarter, day_of_year, month_sin, month_cos. No current/future price is used. Calendar fields include leap-year day-of-year and deterministic month sine/cosine; these are representations, not claims of established seasonality.

Day 5 forecast the next observed record without knowing its eventual date. To match that information set strictly, use the 21 `historical_only_feature_names`. The full 27-feature list is valid only for a date-known scenario and must be labeled as additional information in Day 7 comparisons. Dates of future market reports are not guaranteed known operationally; this dataset does not establish that availability. Target-date gaps are elapsed days (1 means consecutive dates), not missing-day counts.

## Leakage checks and Day 7 use

The real pipeline independently reconstructs every retained feature from array prefixes (5,091 rows) and compares all feature values. It also checks all 1080 validation/test targets against immutable Day 5 forecast records. Unit tests mutate current/future modal/min/max prices and verify that earlier/current-row predictors do not change; exact series remain isolated.

Precomputing these causal features is consistent with Day 5 walk-forward evaluation: after a validation/test outcome is observed it can enter the next row's history. It is not a simultaneous multi-step forecast of the whole holdout. Model fitting, scaling, imputation (if later needed), encoding and selection must use training history only, with validation tuning and final test scoring. The 63 warm-up observations can supply lag context but cannot be supervised training rows; retain the same validation/test dates and disclose that ML training has fewer usable rows than baseline history.

No model was trained, no feature was selected using test scores/correlations, and no diagnostic target correlations were computed. Day 4 selected the cohort retrospectively; limited history, irregular reporting, stale endpoints and unknown publication/revision timestamps still limit generalization. Availability of preceding prices is assumed from recorded observation dates, including lagged min/max. Production use must verify publication timing.

## Reproduction

Run `.\.venv\Scripts\python.exe scripts/build_features.py`. Outputs: canonical feature CSV, feature_metadata.json, feature_summary.json, feature_series_summary.csv and this report. Inputs, code and output hashes support audit and deterministic reruns. No new dependencies or downloads are required.

Day 7: train and compare ML models against the immutable Day 5 benchmarks, with explicit information-availability rules and the unchanged chronological targets.
