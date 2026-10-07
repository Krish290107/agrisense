# AgriSense

AgriSense is an agricultural market intelligence project for **Gujarat mandi prices**. It uses historical market data to show price trends, generate a **next-observation price estimate**, compare supported markets, and estimate gross proceeds for a quantity entered by the user.

The project includes a reproducible data pipeline, forecasting experiments, a FastAPI backend, SQLite storage, and a Next.js dashboard.

## Live Demo

- **Frontend:** https://agrisense-web-v2.vercel.app
- **Backend:** https://agrisense-4lqq.vercel.app
- **API docs:** https://agrisense-4lqq.vercel.app/docs

The live frontend and backend have been verified end-to-end.

> AgriSense predicts the **next reported market observation**. It does not predict “tomorrow” or a fixed 7/30-day future price, and it should not be treated as financial or selling advice.

## What You Can Do

- Select Onion, Potato, or Tomato and a supported market series.
- View recent historical mandi prices.
- Generate a next-observation price estimate.
- See the forecasting method and historical MAE for that series.
- Compare supported markets for the same commodity.
- Enter quantity in quintals and compare estimated gross proceeds.
- View recently generated forecasts.

## Data and Scope

AgriSense uses historical daily commodity-price data for India, filtered to **Gujarat** and the selected commodities.

Source: [Daily Commodity Prices India](https://www.kaggle.com/datasets/khandelwalmanas/daily-commodity-prices-india)

| Item | Value |
| --- | --- |
| Commodities | Onion, Potato, Tomato |
| Clean observations | 39,630 |
| Historical series | 229 |
| Production-supported series | 9 |
| Date range | 2024-01-01 to 2025-12-29 |
| Price unit | INR/quintal |

A forecasting series is identified by **state + district + market + commodity + variety + grade**. Missing dates are not filled with artificial prices.

## Forecasting Approach

AgriSense tested simple forecasting baselines and classical machine-learning models using chronological evaluation.

| Model group | Macro test MAE (INR/quintal) |
| --- | ---: |
| Selected baselines | **119.55** |
| Experimental ML | 136.20 |

The selected baseline policy performed better on all **9/9 supported series**, so the production system uses the stronger validated approach rather than forcing ML into production.

Current production policy:

- **7 series:** latest observed price (`naive`)
- **2 series:** mean of the latest 7 observations (`rolling_mean_7`)
- If a rolling-mean series has too little history, it falls back to the latest valid observation.
- If no valid history exists, the API returns unavailable/null instead of inventing a price.

The ML code and evaluation results are kept as experiments and comparisons.

## Architecture

```text
Historical market data
        ↓
Import → Cleaning → EDA
        ↓
Baseline + ML evaluation
        ↓
Validated forecast policy
        ↓
SQLite database
        ↓
FastAPI backend
        ↓
Next.js dashboard
        ↓
Forecast + market comparison + proceeds calculator
```

## Project Structure

```text
agrisense/
├── backend/          FastAPI application and forecast/decision APIs
├── frontend/         Next.js dashboard
├── configs/          Data configuration and forecast policy
├── data/             Deployment SQLite database + local data directories
├── database/         SQLite schema and repository layer
├── ml/               Experimental ML workspace
├── reports/          EDA, evaluation metrics and figures
├── scripts/          Data, training and verification scripts
├── tests/            Python regression tests
├── app.py            Vercel FastAPI entrypoint
└── README.md
```

## Quick Start

### 1. Clone and set up Python

```powershell
git clone https://github.com/Krish290107/agrisense.git
cd agrisense
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Install the data/ML dependencies only if you want to rerun the research pipeline:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
```

### 2. Configure environment files

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item frontend\.env.example frontend\.env.local
```

The defaults are set for a local frontend on port `3000` and backend on port `8000`.

### 3. Run the backend

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --reload --port 8000
```

Backend: `http://127.0.0.1:8000`  
API docs: `http://127.0.0.1:8000/docs`

### 4. Run the frontend

Open another terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Frontend: `http://localhost:3000`

## Main API Endpoints

```text
GET  /health
GET  /api/v1/forecast/series
GET  /api/v1/forecast/series/{series_id}/history
POST /api/v1/forecast
GET  /api/v1/forecast/series/{series_id}/forecasts
GET  /api/v1/decision/markets?series_id={series_id}
```

## Testing

Python:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Frontend:

```powershell
cd frontend
npm test
npm run typecheck
npm run lint
npm run build
```

## Deployment

The live project uses Vercel for both the frontend and backend. A populated `data/agrisense.db` is included as the deployment seed database. On Vercel, the backend copies it to temporary writable storage so forecast generation can run normally.

This is suitable for the current **portfolio/demo deployment**, but new forecast writes are **not durable across serverless instance replacement**. A full production version should use durable hosted storage such as PostgreSQL.

## Limitations

- Prices are historical, not live market feeds.
- Forecasts cover only the 9 validated production series.
- The target is the next reported observation, not a fixed future date.
- Historical MAE describes past evaluation performance and is not a guaranteed future error range.
- Market comparison and proceeds calculations are decision-support information, not a recommendation to buy or sell.

## Author

**Krishkumar**  
B.Tech CSE, IIT Patna  
GitHub: [Krish290107](https://github.com/Krish290107)
