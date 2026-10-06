# Day 14 — Final release and README usage guide

**Owner:** Krishkumar · **Roll No:** 2401CS83 · **Institution:** IIT Patna
**Repository:** https://github.com/Krish290107/agrisense
**Verified:** 6 October 2026
**DAY 14 DOWNLOADS: None.**

## Release outcome

Complete for local academic submission and source review. The final [README](../README.md) replaces the incremental roadmap with architecture, data provenance, scientific results, supported markets, setup, environment configuration, database prerequisites, run commands, dashboard walkthrough, API examples, testing, deployment boundaries and future work. No demo video is required or planned.

Fresh-clone documentation explicitly distinguishes source-only fixture verification from a real-data installation. The frozen database workflow requires matching ignored canonical/provenance/model artifacts; it cannot be reproduced from the tracked source alone or an arbitrary newer CSV. The existing import/rebuild commands and research guides are linked, with no manual SQL-table setup or bypass of provenance checks.

## Final verification

| Check | Result |
| --- | --- |
| Python regression suite | PASS — 91 tests |
| Frontend tests | PASS — 11 tests |
| TypeScript / lint / production build | PASS |
| Python dependency consistency | PASS — pip check |
| Fixture HTTP/API-client smoke | PASS — health, OpenAPI, discovery, history, generation, saved history, decision support and calculator |
| Canonical temporary rebuild and HTTP smoke | PASS — two imports with identical counts; real client verified both rolling series |
| Database integrity / policy | PASS — schema v1; 39,630 observations, 229 series, 9 policies; 7 naive and 2 rolling-mean-7 |
| Protected scientific artifacts | PASS — 87 hashes checked before/after rebuild; scientific files unchanged |
| CI configuration | PASS — YAML, triggers, permissions, command paths and lockfile consistency; hosted run not performed |
| Documentation | Internal links checked; setup/run/test commands match existing files and scripts |

Temporary rebuild retained one model metadata record, 405 evaluations and seven ingestion records. The smoke flow generated exactly two explicit forecasts in disposable storage; repeats and comparisons added none. The working SQLite database was not modified. Dahod Onion and Potato estimates remained INR 1,442.857143 and INR 1,428.571429 respectively, calculated from actual imported data.

## Scientific status

The README reports Day 5 baseline macro test MAE 119.55 versus Day 7 ML 136.20 INR/quintal, with baselines winning all nine series. Production remains baseline-only and predicts the next observed record, not a fixed calendar horizon. ML, wider coverage and fresh out-of-time evaluation remain future research. Previously examined historical test dates, missing observations and shock sensitivity are visible limitations.

## Deployment readiness and remaining boundaries

The standard Next.js build, FastAPI entry point and actual environment names are documented. No tracked Vercel-specific deployment configuration was found. Existing user-confirmed frontend/backend URLs remain in the README as historical references. Day 14 web requests could not access the frontend, backend health or supported-series URLs; this tool result does not prove an outage and is not a fresh deployment pass. No remote settings, deployment, credentials or tags were changed.

Local SQLite is suitable for local/project use, not durable serverless storage. Durable hosted production persistence needs an external database and adapter; that is not implemented by changing `DATABASE_URL` alone. Hosted CI execution and visual desktop/mobile interaction checks remain unperformed, explicitly separate from the passing local programmatic checks. Optional screenshots are not a submission requirement.

Only README, this report and the progress summary were changed. No files removed, dependencies added, source refactored, model retrained or metrics altered. Historical day reports remain historical evidence. Days 1–14 local work is complete; the project is submission-ready with these stated hosting/data limitations.
