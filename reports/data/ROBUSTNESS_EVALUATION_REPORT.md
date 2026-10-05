# Day 8 — Robust evaluation and final forecasting policy

Krishkumar | Roll No: 2401CS83 | IIT Patna | https://github.com/Krish290107/agrisense

## Objective and evidence boundary

Carry forward a defensible strategy without optimizing against known test outcomes. All nine exact six-field identities remain separate. Day 5 and Day 7 dates were already examined during development: this is a reused historical benchmark, not a pristine holdout or independent replication. No significance or live-production guarantee is claimed.

## Historical reconstruction

Independently reconstructed all 126 baseline metric rows, 7,560 baseline predictions and 540 ML predictions; MAE/RMSE/sMAPE agree within numerical tolerance. Baseline MAE 119.550; original ML MAE 136.198 INR/quintal. Baseline wins all nine series. Pooled RMSE favors original ML (225.505 versus 233.924), so lower MAE does not mean uniformly smaller tail loss. Equal series sizes make pooled MAE equal macro MAE; pooled RMSE differs from mean per-series RMSE.

CSV reconstruction swaps ranks 4/5 for Bilimora Onion validation rolling_mean_7/rolling_median_5: their MAEs tie within 1e-9 INR. Raw floating-point tie ordering is not substantive evidence. Selected winners remain identical; historical ranks and files are preserved.

## Chronological robustness design

Three successive 20-record blocks within the existing 60-record test per series; frozen Day 7 configurations refit at each origin on own earlier feature rows. One-step features and baseline history update after each actual. No tuning or policy reselection.

There are 27 fit origins (three per series), not 27 independent experiments. Blocks have different calendar boundaries across markets and are adjacent, dependent and small. No earlier origins were scored with configurations selected on later validation data. Initial TRAIN alone fixes each series' 95th percentile absolute percentage-change shock threshold and rolling_std_7 terciles. Shock is strict greater-than and post-hoc only; volatility uses seven past observations. Gap days are elapsed calendar days. All seven original baseline formulas are recomputed from original prior prices and checked against saved predictions. ml_frozen is the saved Day 7 prediction; ml_refit uses unchanged configuration refitted on expanded history at each block origin. No outcome at/after an origin enters that fit. No target-date feature is passed to ML. Earlier actuals within a block update features; this is not a 20-step forecast issued at one time.

| window | method | observations | mae | rmse | bias |
| --- | --- | --- | --- | --- | --- |
| 1 | ml_frozen | 180 | 154.936 | 271.867 | 66.293 |
| 1 | ml_refit | 180 | 154.936 | 271.867 | 66.293 |
| 1 | selected_baseline | 180 | 134.643 | 279.142 | 35.357 |
| 2 | ml_frozen | 180 | 106.77 | 160.472 | 16.164 |
| 2 | ml_refit | 180 | 104.993 | 157.529 | 7.711 |
| 2 | selected_baseline | 180 | 92.56 | 158.654 | -8.75 |
| 3 | ml_frozen | 180 | 146.888 | 229.989 | 5.226 |
| 3 | ml_refit | 180 | 147.642 | 230.814 | 1.424 |
| 3 | selected_baseline | 180 | 131.448 | 247.124 | -14.107 |

## Stability and policy decision

| market | commodity | variety | selected_method | robustness_mae | worst_window_mae | window_mae_std | ml_refit_mae |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Bilimora | Onion | Nasik | naive | 31.667 | 45.0 | 12.472 | 66.065 |
| Dahod (Veg. Market) | Onion | Onion | rolling_mean_7 | 185.952 | 214.286 | 26.032 | 195.903 |
| Dahod (Veg. Market) | Potato | Potato | rolling_mean_7 | 85.0 | 107.143 | 15.983 | 87.164 |
| Dahod (Veg. Market) | Tomato | Tomato | naive | 240.0 | 310.0 | 75.609 | 248.729 |
| Kapadvanj | Onion | Other | naive | 23.333 | 43.75 | 15.15 | 43.905 |
| Navsari | Tomato | Other | naive | 290.833 | 450.0 | 127.166 | 296.243 |
| Kapadvanj | Potato | Other | naive | 30.833 | 71.25 | 28.583 | 38.208 |
| Bilimora | Potato | Other | naive | 40.0 | 70.0 | 26.771 | 80.444 |
| Bilimora | Tomato | Other | naive | 148.333 | 165.0 | 11.785 | 166.053 |

Against block-refitted ML, retained baselines have lower aggregate per-series MAE in 9/9 series and ML in 0/9. These diagnostics do not authorize switching based on known test outcomes. Window winners are retrospective only (robustness_window_winners.csv); window mean, median, population SD, best and worst MAE for every method/identity are in robustness_stability.csv. Retain the original validation-selected policy because its overall MAE evidence, simplicity and interpretability remain preferable; individual wins and pooled RMSE differences do not establish a robust replacement rule.

Block-refitted ML wins 3/27 individual series-block comparisons, although baseline pooled MAE is lower in each of the three blocks. The first block is the hardest overall for the retained policy (MAE 134.643); the worst individual block is Navsari Tomato block 1 (450.000). Per-series baseline winners can change, so the selected method is not claimed optimal in every period.

## Commodity, shocks, gaps and bias

| commodity | method | mae | bias | over_rate | under_rate |
| --- | --- | --- | --- | --- | --- |
| Onion | ml_frozen | 101.724 | 25.703 | 0.717 | 0.283 |
| Onion | ml_refit | 101.958 | 24.772 | 0.733 | 0.267 |
| Onion | selected_baseline | 80.317 | -6.905 | 0.228 | 0.233 |
| Potato | ml_frozen | 68.49 | -15.131 | 0.483 | 0.517 |
| Potato | ml_refit | 68.606 | -20.084 | 0.417 | 0.583 |
| Potato | selected_baseline | 51.944 | -10.873 | 0.244 | 0.211 |
| Tomato | ml_frozen | 238.381 | 77.111 | 0.644 | 0.356 |
| Tomato | ml_refit | 237.008 | 70.741 | 0.594 | 0.406 |
| Tomato | selected_baseline | 226.389 | 30.278 | 0.317 | 0.3 |

| shock | method | observations | mae | rmse |
| --- | --- | --- | --- | --- |
| False | ml_frozen | 494 | 111.967 | 183.071 |
| False | ml_refit | 494 | 111.856 | 182.526 |
| False | selected_baseline | 494 | 89.929 | 175.045 |
| True | ml_frozen | 46 | 396.415 | 486.869 |
| True | ml_refit | 46 | 393.607 | 486.837 |
| True | selected_baseline | 46 | 437.655 | 559.749 |

| gap_band | method | observations | mae | bias |
| --- | --- | --- | --- | --- |
| 1 day | ml_frozen | 447 | 131.618 | 29.679 |
| 1 day | ml_refit | 447 | 130.708 | 25.441 |
| 1 day | selected_baseline | 447 | 112.416 | 5.609 |
| 2-3 days | ml_frozen | 76 | 126.693 | 15.728 |
| 2-3 days | ml_refit | 76 | 129.689 | 11.942 |
| 2-3 days | selected_baseline | 76 | 110.432 | -2.82 |
| 4+ days | ml_frozen | 17 | 299.132 | 77.711 |
| 4+ days | ml_refit | 17 | 298.813 | 76.312 |
| 4+ days | selected_baseline | 17 | 347.899 | -2.521 |

Across all commodities, 46/540 observations qualify as shocks. Their baseline MAE is 437.66 versus 89.93 on ordinary observations; these 8.5% of targets contribute about 31.2% of baseline absolute loss. Refitted ML reduces shock MAE to 393.61 but raises ordinary-period MAE to 111.86. Long-gap (4+ days) ML MAE is 298.81 versus baseline 347.90; this diagnostic improvement is based on only 17 targets, and no gap-switching hybrid is selected from test outcomes. Baseline error is not monotonically increasing between the first two gap buckets.

For Tomato, 13 shocks have baseline MAE 848.08 versus 177.99 for 167 ordinary targets; refitted ML shock MAE is 682.02. Tomato baseline MAE increases from 207.10 for one-day gaps to 582.14 for 4+ days, but the latter contains just seven observations. Baselines retain lower overall Tomato MAE and lower error in all three historical-volatility bands. Overall mean signed error is +4.17 for baselines versus +25.14 for refitted ML; commodity-level biases differ and cancel in the aggregate.

Tomato has the largest commodity MAE with available inputs; this does not prove inherent unpredictability or a causal explanation. Sharp movements and reporting gaps are associated diagnostics, not causes. Only 17 targets have gaps of four or more days; subgroup estimates are noisy and mixtures of different series. Commodity-specific shock/gap/volatility counts and errors are in robustness_regime_metrics.csv. Linear versus tree-family shock diagnostics appear in robustness_family_metrics.csv; model family is confounded with series and cannot be interpreted as a controlled family comparison. Over/under rates use a 1e-9 tolerance; exact/tolerance ties account for the remainder.

## Largest misses

| market | commodity | date | actual | prediction | absolute_error | previous_price | price_change | gap_days | historical_volatility |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Navsari | Tomato | 2025-08-25 | 2500.0 | 4500.0 | 2000.0 | 4500.0 | -2000.0 | 1 | 1024.985 |
| Navsari | Tomato | 2025-10-12 | 2500.0 | 1325.0 | 1175.0 | 1325.0 | 1175.0 | 1 | 151.383 |
| Dahod (Veg. Market) | Tomato | 2025-10-27 | 1000.0 | 2000.0 | 1000.0 | 2000.0 | -1000.0 | 4 | 214.92 |
| Navsari | Tomato | 2025-08-24 | 4500.0 | 3500.0 | 1000.0 | 3500.0 | 1000.0 | 1 | 933.822 |
| Navsari | Tomato | 2025-10-27 | 1000.0 | 2000.0 | 1000.0 | 2000.0 | -1000.0 | 8 | 127.359 |

Rows are retained. The full worst-error table includes original and refitted ML. Shock classification uses target outcomes only for this diagnostic table, never for fitting or prediction.

## Final policy and fallback

configs/forecast_policy.json is derived from best_baselines.csv, not the prompt or test winners: seven naive series and two rolling_mean_7 series (Dahod Onion and Potato). It stores full identity, parameters, minimum history, benchmark MAE, version and status. The baseline policy is selected for the next project stage; ML remains experimental/not selected and all artifacts remain intact. A recognized rolling series with insufficient valid trailing history falls back to its last finite positive observation. No valid prior observation returns insufficient_history with null prediction. Unknown exact identity returns unrecognized_series. Mixed identities, duplicate/unsorted dates and invalid policy definitions raise errors. Missing/invalid prices are never fabricated or interpolated. Caller must supply only already observed history; this local helper is not an API or fixed-date forecast service.

Reloaded JSON reproduces all 540 selected historical predictions. Only chronological existing candidate history is accepted. No zero-price placeholder is emitted.

## Uncertainty

Skipped: validation residuals already served method selection; no independent calibration period reserved. No claimed confidence bands.

## Limitations and Day 9 readiness

Only roughly two source years and fewer than two years for individual series, irregular observations, nine retrospectively chosen strong candidates, previously examined tests, dependent small windows, abrupt shocks, unverified publication/revision timing and no weather/arrivals/demand inputs limit generalization. One-step next-observed-record prediction differs from a forecast for a specified future date. Historical performance does not guarantee live accuracy. Fresh later data and independent calibration are required before stronger deployment or interval claims. No UI, API, deployment or historical data changes are part of Day 8. Day 9 can persist market observations, forecasts, this policy and model/evaluation metadata.
