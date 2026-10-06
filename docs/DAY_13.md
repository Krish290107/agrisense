# Day 13 — Reliability, automation and repository hygiene

**Owner:** Krishkumar · **Roll No:** 2401CS83 · **Institution:** IIT Patna  
**Repository:** https://github.com/Krish290107/agrisense  
**Verified:** 6 October 2026  
**DAY 13 DOWNLOADS: None.**

## Completed

- Added one read-only-permission CI workflow for Python tests, dependency consistency, lockfile-based frontend installation, typecheck, lint, frontend tests, production build and cross-language HTTP smoke verification. No datasets, model training, local database or secrets are required by CI.
- Added `scripts/verify_system.py`: starts a temporary-database API on an automatically allocated loopback port and invokes the actual TypeScript API client and calculator through `frontend/scripts/smoke.mjs`. Servers and temporary databases are cleaned up. Default mode reuses existing fixtures; `--rebuild` reuses Day 9 canonical import/verification helpers without replacing Day 9 reports or the user's database.
- Smoke coverage includes health, OpenAPI generation, supported series, history, rolling/fallback/no-history forecasts, saved history, decision comparisons, percentage/proceeds arithmetic and repeated-request idempotency. Comparison requests save nothing. Successful explicit forecasts save exactly one row per tested series.
- Backend origins now reject malformed configuration, credentials, paths and wildcards with a sanitized startup message; default local origins remain supported. Frontend API configuration rejects credentials/query/fragment URLs before issuing requests. Added configuration and CORS regressions.
- Changed backend requirements from exact pins to the requested minimum-version convention. No installed packages were upgraded. Existing scientific dependencies were retained because they are used by the pipeline/tests.
- Added a test package marker to make shared fixture imports deterministic across environments. Removed only the now-obsolete `.github/workflows/.gitkeep` placeholder.

## Verification results

| Category | Result |
| --- | --- |
| Python regressions | PASS — 91 tests, also run in an isolated copy containing only tracked/new files |
| Frontend regressions | PASS — 11 tests |
| Typecheck / lint / production build | PASS |
| OpenAPI / HTTP / frontend contracts | PASS — actual API responses consumed by the real typed client |
| Fixture smoke without local datasets or environment files | PASS |
| Database rebuild / second import | PASS — identical counts and exact canonical price/provenance roundtrips |
| Integrity / foreign keys / policy lookup | PASS — existing Day 9 verifier |
| Production policy / scientific artifacts | PASS — 87 protected hashes verified before/after rebuild; no scientific files changed |
| Dependency consistency | PASS — pip check; package manifest matches lockfile |
| CI | YAML and workflow structure checked; local commands pass; hosted execution not performed |
| Repository hygiene | No tracked generated caches/databases/logs, obvious secret matches or machine-specific runtime paths found |

Fresh-copy verification excluded ignored raw/canonical data, model binaries, SQLite and `.env` files. Python tests and fixture HTTP smoke both passed there. This demonstrates that CI's tests do not silently depend on the developer's dataset. Real-data rebuild remains a local optional check requiring the existing canonical/provenance/model artifacts; those large artifacts are intentionally not committed.

### Temporary rebuild counts

| Table | First import | Second import |
| --- | ---: | ---: |
| Observations | 39,630 | 39,630 |
| Series | 229 | 229 |
| Policies | 9 | 9 |
| Policy versions | 1 | 1 |
| Models (experimental metadata) | 1 | 1 |
| Evaluations | 405 | 405 |
| Ingestions | 7 | 7 |
| Forecasts before smoke | 0 | 0 |

Integrity was `ok`. HTTP smoke subsequently created exactly two explicit forecasts in that disposable database; retries and comparisons added none. The working database was not used for writes.

Real results from the rebuilt database: Dahod Onion latest INR 1,300 on 2025-11-04, next-observation estimate INR 1,442.857143; Dahod Potato latest INR 1,500 on 2025-11-03, estimate INR 1,428.571429. These were calculated from imported observations, not hard-coded expectations. All nine policies remain active, with seven naive and two rolling-mean-7 methods; ML remains experimental.

## Configuration, cleanup and limits

The database default remains repository-relative `sqlite:///data/agrisense.db`; explicit unsupported engines fail and API errors remain sanitized. Request-scoped SQLite connections, schema version 1, CORS defaults, forecast routes, selectors, chart and decision semantics remain intact. No environment file or deployed configuration was edited. Existing ignore rules already cover credentials, raw data, generated databases, caches and build outputs; useful local build/runtime caches were retained.

Security checks were limited to obvious tracked credentials, paths, SQL construction and error exposure, not a comprehensive vulnerability audit. Earlier documented dependency limitations were not re-audited or claimed resolved. Node's existing module-type inference warning is non-failing and was not used as a reason to alter module configuration.

The workflow uses the official [checkout](https://github.com/actions/checkout), [setup-python](https://github.com/actions/setup-python) and [setup-node](https://github.com/actions/setup-node) actions with Python 3.13 and Node 24 project settings. Hosted Linux execution and dependency installation remain to be observed in the first CI run; local checks do not claim a hosted CI success.

Ready for Day 14 work. Visual browser/interaction verification remains unperformed and should be included in final release verification. No deployment, final README overhaul, screenshots, model retraining or new product features were attempted.
