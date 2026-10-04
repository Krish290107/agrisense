# AgriSense

**Project owner:** Krishkumar | **Roll No:** 2401CS83 | **Institution:** IIT Patna

**GitHub repository:** https://github.com/Krish290107/agrisense

Agricultural Price Forecasting and Market Decision Support — a 14-day college project.

Day 1 provides the working Next.js frontend and FastAPI backend. Day 2 adds local CSV import, provenance, quality checks and a Gujarat scope recommendation using the supplied Kaggle files. Forecasting, training, production cleaning and a database remain later-day work.

See [the progress record](docs/PROGRESS.md) for installed versions, actual verification results, and remaining manual steps.

## Day 2: reproduce the real-data profile

Source: [Daily Commodity Prices India on Kaggle](https://www.kaggle.com/datasets/khandelwalmanas/daily-commodity-prices-india), published by Manas Khandelwal. The supplied `2024.csv` and `2025.csv` contain 11,363,982 rows in total. Gujarat has 523,868 rows; its Onion, Potato and Tomato subset has 39,634 rows. The title does not establish complete history: the 2025 file has only 342 distinct dates.

```powershell
cd C:\Zekrui\agrisense
.\.venv\Scripts\python.exe -m pip install -r requirements-data.txt
.\.venv\Scripts\python.exe scripts\import_market_data.py data\raw --source kaggle_daily_india --kind historical --date-format "%Y-%m-%d"
.\.venv\Scripts\python.exe scripts\profile_market_data.py --state Gujarat --commodities Onion Potato Tomato
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test_market_data.py" -v
```

The original CSVs remain unchanged in `data/raw/`. Reimporting identical content safely skips it. Chunked reads handle the large input files; only the selected state/commodities are retained for detailed profiling. A fresh clone must obtain these ignored data files separately.

Read [the data profile](reports/data/DATA_PROFILE.md), [the compact recommended scope](reports/data/recommended_scope.csv), and [Day 2 instructions](docs/DAY_02.md). The recommended scope has **15 combinations across three commodities**, explicitly using shorter history: no unchanged variety/grade series reaches the original 700-day screen. No grades are merged and no prices are fabricated. Price units are INR/quintal according to the Kaggle publisher; arrivals are absent.

## Existing deployed applications

- Backend project `agrisense-api`: https://agrisense-4lqq.vercel.app
- Frontend project `agrisense-web-v2`: https://agrisense-web-v2.vercel.app

These are the user-confirmed working deployments. Day 2 tools run locally and require no Vercel action.

## Start the existing workspace

Open two PowerShell terminals in VS Code. Keep both running. These commands assume this workspace is at `C:\Zekrui\agrisense`; change that path if you move the project.

**Terminal 1 — backend**

```powershell
cd C:\Zekrui\agrisense
.\.venv\Scripts\python.exe -m uvicorn backend.app:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend**

```powershell
cd C:\Zekrui\agrisense
. .\scripts\use-node.ps1
cd frontend
npm.cmd run dev
```

The dot followed by a space in `. .\scripts\use-node.ps1` selects the project's Node.js 24 LTS for that terminal. Repeat it in each new frontend terminal. `npm.cmd` avoids PowerShell's `npm.ps1` execution-policy issue. Python activation is unnecessary because the command uses the root environment's executable directly.

Open:

| Address | Expected result |
| --- | --- |
| <http://localhost:3000> | AgriSense homepage and backend connection indicator |
| <http://127.0.0.1:8000/health> | `{"status":"ok","service":"agrisense-api"}` |
| <http://127.0.0.1:8000/docs> | Interactive FastAPI API documentation |

Press **Ctrl+C** in each terminal to stop its service.

## Set up a fresh clone

The original workspace already has installed dependencies. Use this section after cloning onto another computer or restoring dependencies.

Install Python 3.13 and Git for Windows if missing, then reopen VS Code. Python's Windows installer should include the `py` launcher. Official downloads: [Python for Windows](https://www.python.org/downloads/windows/) and [Git for Windows](https://git-scm.com/downloads/win).

Check the tools:

```powershell
cd C:\Zekrui\agrisense
git --version
py -0p
py -3.13 --version
```

Install the portable project Node.js and verify it:

```powershell
.\scripts\setup-node.ps1
. .\scripts\use-node.ps1
node --version
npm.cmd --version
```

The setup script downloads Node.js 24 into the ignored `.tools/node/` directory and checks its download checksum. It does not replace a system-wide Node.js installation. If PowerShell blocks this project's scripts, permit scripts for this terminal only and rerun them:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

Install Python dependencies into one root environment:

```powershell
if (-not (Test-Path .\.venv\Scripts\python.exe)) {
    py -3.13 -m venv .venv
}
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Create local settings only when absent, then install the frontend's locked dependencies:

```powershell
if (-not (Test-Path backend\.env)) {
    Copy-Item backend\.env.example backend\.env
}
if (-not (Test-Path frontend\.env.local)) {
    Copy-Item frontend\.env.example frontend\.env.local
}
cd frontend
npm.cmd ci
```

Use the two startup terminals above after installation.

## Configuration and checks

`frontend/.env.local` uses `NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000`. Restart the frontend after changing it. This address is public browser configuration; never put a secret in a `NEXT_PUBLIC_` variable.

`backend/.env` uses `ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000`. These are the browser addresses allowed to call the API. The backend loads this file relative to `backend/app.py`, and environment variables already set by the host take priority. Restart the backend after changing it.

Run frontend checks in a separate terminal, with the development server stopped before building:

```powershell
cd C:\Zekrui\agrisense
. .\scripts\use-node.ps1
cd frontend
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run build
```

The build can run while the backend is stopped. The health request happens in the browser after the page opens.

For a manual connection check, open the homepage with both services running, confirm the successful connection, stop the backend, and click **Retry**. You should see a loading state followed by a failed connection. Restart the backend and retry to recover. Check the browser's Network panel for the `/health` request.

If the frontend starts on port 3001 because 3000 is busy, stop the conflicting server and restart on 3000, or explicitly add the new frontend origin to `ALLOWED_ORIGINS` and restart the backend. A successful direct `/health` response alone does not verify browser CORS.

## Project guide

- [Day 1 files, tools, and request flow](docs/DAY_01.md)
- [Day 2 import, profiling and commands](docs/DAY_02.md)
- [Data sources and provenance](docs/DATA_SOURCES.md)
- [Data dictionary and future prediction rules](docs/DATA_DICTIONARY.md)
- [Commit and GitHub upload](docs/GITHUB_SETUP.md)
- [Future two-project Vercel deployment](docs/VERCEL_DEPLOYMENT.md)
- [Progress and verification evidence](docs/PROGRESS.md)
- [Day 1 presentation notes](docs/DAY_01_PRESENTATION.md)

The raw CSVs and immutable imports remain local and ignored. `tests/` contains synthetic tool-verification inputs only. `ml/`, `notebooks/`, `database/`, `data/interim/`, `data/processed/`, and `.github/workflows/` reserve space for future work.

## Roadmap

1. setup
2. real data
3. cleaning
4. exploration
5. baselines
6. features
7. training
8. evaluation
9. database
10. API
11. dashboard
12. selling calculator
13. tests and refresh
14. deployment and presentation

Days 1 and 2 are implemented. Day 3 cleaning decisions are next; full two-year per-series coverage remains a documented data limitation.
