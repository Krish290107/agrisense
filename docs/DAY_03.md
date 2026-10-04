# Day 3: deterministic cleaning

Krishkumar | 2401CS83 | IIT Patna

Repository: https://github.com/Krish290107/agrisense

No downloads or new dependencies are required. Run the existing environment's Python:

```powershell
.\.venv\Scripts\python.exe scripts/clean_market_data.py
```

The command resolves paths relative to the repository, verifies imported historical bundles against their provenance, and streams the national files while retaining only configured Gujarat Onion/Potato/Tomato observations. Original files and Day 2 reports remain unchanged.

## Outputs and rules

- `data/processed/market_prices_clean.csv`: one canonical CSV, sorted by six-field series identity and date; all valid scoped observations, not just recommended markets.
- `reports/data/local/rejected_rows.csv`: excluded rows, reason codes, original values, source hash and record number; ignored by Git.
- [cleaning_summary.json](../reports/data/cleaning_summary.json): actual counts, source/output hashes and overlapping quality metrics.
- [CLEANING_REPORT.md](../reports/data/CLEANING_REPORT.md): compact real-data results and limitations.

Required schema: date, state, district, market, commodity, variety, grade and three prices. Missing columns fail with an actionable error. Invalid dates, missing identity, malformed/nonfinite prices, nonpositive prices, impossible price ordering, conflicting keys and unverified/conflicting units are quarantined. No prices are corrected. Numeric validation uses decimal arithmetic and retains valid source price text.

Whitespace is trimmed/collapsed; spelling and case remain unchanged. FAQ and Non-FAQ, varieties, districts and similarly named markets remain separate. Conflicts are detected before removing any invalid row or exact duplicate. Identical raw copies retain the lowest source hash/record; equivalent nonconflicting keys are counted separately. All excluded rows are audited, including duplicates. Issue counts can overlap, while removed-row accounting is disjoint.

No filling, interpolation, extra calendar dates, aggregation, features, splits or models are generated. `modal_price` is the future target. Short/sparse series remain present for Day 4 analysis; cleaning does not certify model eligibility or solve the incomplete two-year history. Market-label crosswalks are not assumed.

## Verification

Focused cleaning tests and Day 2 regression tests use tiny isolated test inputs:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -p "test*market_data.py" -v
```

The real-data results and final reproducibility checks are recorded in [PROGRESS.md](PROGRESS.md).

## Repository cleanup

Removed obsolete initial GitHub and future Vercel setup walkthroughs; repaired their documentation references and removed redundant upload steps from the Day 2 guide. Runtime instructions and confirmed deployment URLs remain in README. Next.js-generated `frontend/AGENTS.md` and its `CLAUDE.md` reference remain, as do active Node helpers, application source, configurations, tests, raw data and intentional placeholders. Ignore rules additionally cover Python coverage files, temporary/editor files and rejected-row audits.

Next: Day 4 exploratory analysis within each exact series.
