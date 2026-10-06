# Day 12 — Market decision support

**Owner:** Krishkumar · **Roll No:** 2401CS83 · **Institution:** IIT Patna  
**Repository:** https://github.com/Krish290107/agrisense  
**Verified:** 6 October 2026  
**DAY 12 DOWNLOADS: None.**

Implemented the four core features inside the existing dashboard: neutral price signal, supported-market comparison, quantity/gross proceeds calculator, and a deterministic summary. No dependencies, datasets, models, policy changes or schema migrations were added. No files were removed.

## API and interpretation

`GET /api/v1/decision/markets?series_id=<exact-series-id>` uses the selected series to choose its commodity and preferred variety/grade scope. Only active policy series qualify. Two or more distinct markets with matching commodity, variety and grade produce an exact comparison; otherwise the response broadens to the commodity and explicitly warns about variety/grade differences. Every row retains the complete series identity.

The endpoint opens SQLite read-only, takes a consistent transaction snapshot and calls the existing `generate_forecast(..., persist=False)` service. It never writes comparison forecasts or selects experimental ML. Only the existing explicit Generate forecast action saves a forecast. Ordering is forecast descending, then series ID; unavailable estimates sort last. Errors are sanitized.

Difference is forecast minus latest modal price; percentage is difference divided by latest price times 100, calculated with Decimal. Absolute percentage strictly below 2% is **Near**; exactly +2% is **Above**, exactly -2% is **Below**. This fixed presentation threshold was not tuned to historical outcomes. Missing inputs remain null.

The calculator accepts finite positive decimal quantities in quintals. It multiplies unrounded API prices by quantity, displaying INR to two decimal places. It shows gross proceeds at latest and forecast prices, their difference, and estimated proceeds for every comparison. Missing prices, invalid quantities and overflow remain unavailable. Costs are excluded. Summary text uses actual values without external explanations or generative AI.

Dates are historical observation dates, not live prices. Estimates concern the next reported observation, not a fixed calendar horizon. Historical benchmark MAE is context, not a guaranteed error range. Market access, costs and selling decisions are outside this comparison.

## Real-data verification

The actual HTTP endpoint and existing TypeScript API client verified:

| Item | Observed result |
| --- | --- |
| Selected series | Gujarat / Dahod / Dahod (Veg. Market) / Potato / Potato / FAQ |
| ID | `314b4dfffac5b7bc` |
| Latest modal price and date | INR 1,500; 2025-11-03 |
| Method and estimate | rolling_mean_7; INR 1,428.571429/quintal |
| Difference / percentage / signal | -71.428571 / -4.7619047333% / Below |
| 10 quintals, latest-price gross | INR 15,000.00 |
| 10 quintals, forecast-price gross | INR 14,285.71 |
| Gross proceeds difference | INR -714.29 |
| Broader Potato comparison | 3 series: Bilimora (2,800), Dahod (1,428.571429), Kapadvanj (1,200) |
| Exact Potato / Other / FAQ comparison | 2 series: Bilimora and Kapadvanj; no broader-scope warning |
| Forecast persistence check | 5 before and 5 after comparison |

The calculator uses the full estimate before rounding; multiplying a prematurely rounded price would produce a different result.

## Verification

- 4 new backend tests: exact/broader scopes, service reuse, no persistence, identity isolation, baseline methods, missing history, arithmetic/thresholds and sanitized errors.
- 89 Python regression tests passed, including existing forecasting/database/API coverage.
- 10 frontend tests passed, including new calculation, quantity validation and decision client/contract coverage.
- Typecheck, lint and production build passed.
- Live local HTTP results passed the actual frontend response validator and calculator; exact-match and broader scopes both verified.
- Browser visual/interaction verification was not performed. Responsive cards reuse the existing layout and adapt to available width.

Next: Day 13 — end-to-end reliability, automation and project cleanup.
