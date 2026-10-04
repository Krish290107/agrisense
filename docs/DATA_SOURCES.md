# Data sources and provenance

Project owner: **Krishkumar** | Roll No: **2401CS83** | **IIT Patna**

Repository: https://github.com/Krish290107/agrisense

Checked on **October 4, 2026**. The project state is **Gujarat**, as requested by the owner.

## Source actually used

The user supplied `data/raw/2024.csv` and `data/raw/2025.csv` and identified [Daily Commodity Prices India on Kaggle](https://www.kaggle.com/datasets/khandelwalmanas/daily-commodity-prices-india) as their source. The public Kaggle page returned HTTP 200. Its embedded Dataset metadata identifies **Manas Khandelwal** as the republisher and attributes the upstream data to the Government of India's Open Data Platform.

The publisher states that the data was cleaned, deduplicated and sorted upstream. These files are therefore preserved as the original **Kaggle downloads supplied by the user**, not represented as untouched government exports. We independently check their contents rather than assume the publisher's quality claims. No additional observations were downloaded or generated.

The publisher's column descriptions explicitly specify **INR per quintal** for minimum, maximum and modal prices and ISO `YYYY-MM-DD` dates. The CSVs themselves contain no unit or arrivals columns. Unit provenance is the publisher's declaration, not a row-level unit validation. No quantity units or arrivals values are inferred.

The Kaggle license metadata is **Other (specified in description)**, while its description states **Government Open Data License - India (GODL-India)**. This distinction is preserved in provenance. Attribute both the republisher and the upstream OGD source; verify the applicable terms before redistributing bulk data. The local files' Kaggle version/download time are unknown and were not inferred from the current page. A checksum identifies local content but does not independently match it to a Kaggle release.

## Actual local inventory

| File | Bytes | Rows | Parsed first date | Parsed last date | Distinct dates |
| --- | ---: | ---: | --- | --- | ---: |
| 2024.csv | 532,414,234 | 5,544,500 | 2024-01-01 | 2024-12-31 | 366 |
| 2025.csv | 573,676,886 | 5,819,482 | 2025-01-01 | 2025-12-30 | 342 |
| Total | 1,106,091,120 | 11,363,982 | 2024-01-01 | 2025-12-30 | 708 |

Every original row was counted by the importer. Both files have zero missing/unparseable dates under `%Y-%m-%d`. The 2025 file does not cover every calendar date, and neither the filename nor the dataset title guarantees complete history for a particular market/variety/grade.

SHA-256:

```text
2024.csv  59794b7a4dad2fa5e3f1a116851b584368ca99ce44a9fe90b2638e8a5faf7a60
2025.csv  0070d5c0fd8f95a2268420eaa3f9b712f74bbb179e8c09025c4f32d4999bb45a
```

Originals remain in place. The importer created checksum-named bundles under `data/raw/historical/`, each containing an unchanged `source.csv` and its own `provenance.json`. Metadata records the original filename, source/publisher, import UTC time, unknown acquisition time, bytes, checksum, row count, original headers, date range, parsing rules, units and license/attribution status. Duplicate-content reimports retain existing provenance and skip another copy.

## Gujarat findings and scope

All Gujarat commodities: **523,868 rows**, **707 distinct dates**, **2024-01-01 through 2025-12-29**. The detailed project profile selects exact commodity labels Onion, Potato and Tomato and contains **39,634 rows** across **229 separate market/commodity/variety/grade series**.

| Commodity | Gujarat rows | Distinct dates, pooled across markets | District-market combinations |
| --- | ---: | ---: | ---: |
| Onion | 12,667 | 694 | 57 |
| Potato | 13,002 | 699 | 50 |
| Tomato | 13,965 | 702 | 61 |

Each commodity's observed range is 2024-01-01 to 2025-12-29. These pooled dates are **not** the history of a single forecasting series. See [DATA_PROFILE.md](../reports/data/DATA_PROFILE.md) for actual series and grade coverage.

No unchanged variety/grade series reaches the original **700-day** minimum: the longest span is **675 days**. Rather than silently join grades, the tool reports that strict result and a separately labeled **shorter-history** recommendation using a **600-day** minimum. All other screens remain: at least 365 positive modal observation days, at least 50% calendar coverage, no internal gap over 45 days, identified variety/grade, consistent price units and no unresolved price/date/conflicting-key flags. This yields 60 eligible series; 15 combinations are selected across the three commodities, retaining one explicit variety and grade per combination.

This is approximately 22 months for the recommended series, not a fulfilled two-year target. Many long FAQ series end in early November 2025. Later data contains APMC-suffixed market names (for example Bilimora APMC), sometimes with changed variety/grade labels. Possible renames require a verified crosswalk; neither market labels nor grades are silently merged. Even the reported variety `Other` remains its own source label and does not prove a homogeneous crop variety. These are transparent project choices, not forecasting-accuracy guarantees. Missing calendar dates can be closures or non-reporting, and are never filled with zeroes.

## Earlier official-source investigation

Before the user supplied the Kaggle files, these official sources were investigated:

- [data.gov.in catalog](https://www.data.gov.in/catalog/current-daily-price-various-commodities-various-markets-mandi): HTTP 200; description identifies daily wholesale prices from AGMARKNET/DMI. Rendered resource results were absent.
- [data.gov.in resource](https://www.data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi): HTTP 200; embedded metadata identifies `https://api.data.gov.in/resource/9ef84268-d588-465a-a308-a864a43d0070` with key/offset/limit parameters. Download probes timed out; response/pagination behavior was not verified. No credential was retained in project files or logs.
- The resource's published `Date-Wise-Prices-all-Commodity.xml` asset returned HTTP 403. It was not imported.
- [AGMARKNET](https://agmarknet.gov.in/): HTTP 200 JavaScript shell; no data export obtained.
- [e-NAM AGMARKNET dashboard](https://enam.gov.in/dashboard/agmarknet): HTTP 200; state, district, APMC, commodity and date-range controls were visible, but no rows/export were obtained through available tooling.

No guessed API fetcher was added. These earlier access failures do not block local analysis of the now-supplied files. For longer same-grade history, obtain a genuine additional export/download and rerun the importer. Confirm its source, dates, units, license and grade definitions; do not append daily snapshots and call them a historical backfill. A current snapshot's pagination adds records, not necessarily dates.

## Remaining provenance limitations

- Download/acquisition time and exact Kaggle dataset release for the two supplied files are unknown; import times and local checksums are recorded.
- Price units and upstream transformation/license claims are attributable to the Kaggle publisher; no independent government-to-Kaggle reconciliation was performed.
- Arrivals/quantity fields are absent.
- Full two-year per-series history is not available under unchanged variety/grade identities in this subset. Use the explicitly provisional shorter scope or acquire more compatible observations before claiming otherwise.
