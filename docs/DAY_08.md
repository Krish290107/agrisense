# Day 8 — Robust evaluation and final forecasting strategy

Krishkumar | Roll No: 2401CS83 | IIT Patna  
Repository: https://github.com/Krish290107/agrisense

Status: complete. Downloads: none. Existing dependencies and local artifacts suffice.

Run from the repository:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_robustness.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

`--audit-only` reconstructs the Day 5/7 metrics without generating evaluation outputs.

The evaluator first reconstructs 126 baseline metric rows, checks exact identities and 540 ML targets, verifies source hashes, and preserves the historical benchmark. One nonwinning validation rank pair changes order within floating-point MAE tolerance; this is documented without altering previous results.

Three successive 20-record blocks per series use strictly earlier same-series observations for fitting. ML configurations remain frozen from Day 7; weights refit at block origins. Historical-only features and baseline formulas update after each revealed observation. This is one-step observed-record forecasting, not a 20-step forecast or a new holdout. No configuration selection occurs during Day 8.

The selected baseline policy has MAE **119.55 INR/quintal**, original ML **136.20**, and block-refitted ML **135.86**. Baselines win all nine aggregate series comparisons; ML wins three of 27 individual blocks and helps on post-hoc shock and long-gap subsets. The first pooled block is hardest (baseline MAE 134.64); Navsari Tomato block 1 reaches 450.00. These exceptions and the smaller ML pooled RMSE are retained in the report.

The [policy](../configs/forecast_policy.json) derives from Day 5 validation selection: seven naive series and rolling mean 7 for Dahod Onion and Potato. `load_policy` validates the JSON. `policy_forecast` accepts the exact six-field identity and a chronological DataFrame of completed observations with identity, date and modal_price columns. The caller must exclude unobserved future records. It returns selected/fallback with a finite positive price, insufficient_history with null prediction, or unrecognized_series with null prediction. Short/invalid trailing rolling history falls back to the latest finite positive observation. Mixed identities and duplicate/unsorted dates raise errors. Invalid prices are never imputed. This helper is local; no API or UI is added.

Artifacts:

- [Evaluation report](../reports/data/ROBUSTNESS_EVALUATION_REPORT.md), [summary and hashes](../reports/data/robustness_summary.json), [final per-series table](../reports/data/robustness_final_evaluation.csv).
- Origins, training thresholds, window scores, stability, retrospective window winners, commodity/regime/family diagnostics and worst errors under `reports/data/robustness_*.csv`.
- Local ignored `reports/data/local/robustness_predictions.csv`: 5,400 rows, including seven baseline methods, a selected-baseline alias and two ML update strategies; 540 unique targets.
- Eight reviewed figures under `reports/figures/evaluation/`.

Verification: nine focused tests plus 52 regression tests pass; policy reload reproduces all 540 selected forecasts; baseline formulas reproduce stored values; first-block ML matches Day 7; full rerun reproduces Day 8 output hashes. Protected raw/imported data, cleaned/features, candidates and Day 5–7 artifacts are hashed before and after evaluation. No files were removed.

Shock thresholds use initial-training absolute percentage-change 95th percentiles, with strict greater-than classification used only after outcomes are known. Volatility terciles use initial-training past-seven-observation standard deviations. Observed gaps support buckets 1, 2–3 and 4+ days, with counts 447, 76 and 17. No confidence bands are claimed because validation residuals already served selection and no independent calibration period was reserved.

Limitations: previously examined tests, three dependent blocks, nine retrospectively selected strong series, roughly two source years, irregular reports, unknown release/revision timing, difficult shocks and no external weather/arrivals/demand data. Historical results do not establish live performance or statistical significance.

Next: Day 9 persistence/database layer for market observations, forecasts, policy and model/evaluation metadata.
