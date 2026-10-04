# AgriSense: Day 1 presentation notes

**Project owner:** Krishkumar

**Roll No:** 2401CS83

**Institution:** IIT Patna

**Repository:** https://github.com/Krish290107/agrisense

## 1. Project purpose

AgriSense - Agricultural Price Forecasting and Market Decision Support.
The project will explore how real agricultural price records can inform market decisions.
Day 1 establishes the application foundation; it makes no claims about forecasting accuracy or financial outcomes.

## 2. Day 1 implementation

- Next.js frontend with TypeScript, App Router, Tailwind CSS, and ESLint.
- FastAPI backend with a real `GET /health` endpoint.
- Browser connection indicator with loading, success, failure, a five-second timeout, and retry.
- Local environment configuration, Git exclusions, setup documentation, and future Vercel instructions.

## 3. Explain the connection

The browser loads the page from Next.js on port 3000. Its JavaScript requests
`http://127.0.0.1:8000/health`. FastAPI returns
`{"status":"ok","service":"agrisense-api"}`. The browser validates this response
and updates the connection indicator. CORS permits the two configured local frontend origins.

## 4. Live demonstration

1. Start both services using the README's two-terminal commands.
2. Open `http://localhost:3000` and show the connected indicator.
3. Open `http://127.0.0.1:8000/docs` and demonstrate the health endpoint.
4. Stop the backend, click **Retry connection**, and show the failure state.
5. Restart the backend and retry to demonstrate recovery.
6. Point out that all market and forecasting features are marked **Planned**.

## 5. Evidence and next step

Refer to [PROGRESS.md](PROGRESS.md) for the actual installed versions and verification results.
Day 2 is real data: choose a source and document its fields, coverage, units, and usage terms.
No data collection or later-day functionality has been implemented on Day 1.

## 6. Fourteen-day roadmap

1 setup; 2 real data; 3 cleaning; 4 exploration; 5 baselines; 6 features;
7 training; 8 evaluation; 9 database; 10 API; 11 dashboard; 12 selling calculator;
13 tests and refresh; 14 deployment and presentation.
