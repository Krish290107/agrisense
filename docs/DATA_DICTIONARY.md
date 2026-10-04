# Data dictionary and profiling rules

Project owner: **Krishkumar** | Roll No: **2401CS83** | **IIT Patna**

Repository: https://github.com/Krish290107/agrisense

The supplied Kaggle CSVs have been inspected. Their actual columns are `State`, `District`, `Market`, `Commodity`, `Variety`, `Grade`, `Arrival_Date`, `Min_Price`, `Max_Price`, `Modal_Price`, and `Commodity_Code`. Dates are ISO `YYYY-MM-DD`. The Kaggle publisher specifies INR/quintal for prices; CSV rows contain no explicit unit or arrivals fields. `Commodity_Code` is retained unchanged as an unmapped source identifier. The table below also lists supported aliases for future inputs. Full accepted aliases are in `configs/data_sources.json`; header matching ignores case and punctuation only for finding a mapping. Source headers, spelling, leading zeroes, whitespace and values remain in the immutable CSV.

| Canonical field | Common input names | Meaning / treatment |
| --- | --- | --- |
| `state` | State, State_Name | Geographic identity; required for an identifiable series |
| `district` | District, District_Name | Included in identity so same-named markets are not merged |
| `market` | Market, Market_Name, APMC, APMC's | Reporting market; source naming retained |
| `commodity` | Commodity, Commodity_Name | Source commodity label; no crop categories invented |
| `variety` | Variety, Commodity Variety | Optional; absent/blank stays unknown, separate from known varieties |
| `grade` | Grade, Commodity_Grade | Optional; absent/blank stays unknown, separate from known grades |
| `date` | Date, Arrival_Date, Arrivals_Date, Reported_Date, Price_Date | Source observation/reporting date, not import time; confirm exact semantics |
| `min_price` | Min_Price, Minimum_Price, Min Price (Rs./Quintal) | Source minimum price; denomination must be verified |
| `max_price` | Max_Price, Maximum_Price, Max Price (Rs./Quintal) | Source maximum price |
| `modal_price` | Modal_Price, Modal Price (Rs./Quintal) | Proposed future prediction target, subject to confirmed source semantics |
| `arrivals` | Arrivals, Arrival_Quantity, Arrivals_Quantity, Commodity Arrivals | Optional arrivals quantity; not automatically traded quantity |
| `price_unit` | Price_Unit, Price_Units | Explicit row-level price denomination |
| `quantity_unit` | Quantity_Unit, Arrivals_Unit, Arrival_Unit | Explicit row-level arrivals unit |
| `unit` | Unit, Units | Generic source unit, reported but not assigned to price or quantity automatically |

`Commodity Traded` is not mapped to arrivals: they are different measures. Other columns are retained and reported as unmapped. There are no invented rainfall, weather, soil, transport-cost or production fields.

## Day 2 profiling: parsing without cleaning

- CSV bytes are copied unchanged. CSV parsing keeps every value as a string and retains blank records as missing-value rows. Different row widths, empty/duplicate headers, or ambiguous alias matches produce explicit errors instead of silently dropping data.
- Missing markers for profiling are blank/whitespace, `NA`, `N/A`, `NULL`, `NaN`, `-`, and `--` (case-insensitive). Original marker strings remain untouched.
- Without `--date-format`, only strict `YYYY-MM-DD` is accepted. `01/02/2025` remains a parse failure unless the caller explicitly chooses its meaning, e.g. `%d/%m/%Y` or `%m/%d/%Y`. `%Y` requires a four-digit year. Missing dates and nonmissing parse failures are counted separately.
- Mixed file formats can be imported in separate invocations. Profiling normally uses each file's recorded format. A profiling `--date-format` override applies to every selected file and does not modify provenance.
- Numeric parsing permits ordinary decimal/scientific notation. It does not guess currency signs, comma thousands separators, decimal commas, or unit conversions. Nonfinite values fail parsing. Original numeric text remains unchanged.
- Identity values are not case-folded, spelling-corrected or trimmed into a new label. Missing markers are treated as unknown only in temporary analysis.

An explicit mapping file resolves multiple aliases, for example if both Date and Arrival_Date appear:

```json
{"date": "Arrival_Date"}
```

Save that as a local JSON file and pass `--column-map path\to\mapping.json`. It maps canonical field names to exact original headers. All other fields still use configured aliases. No two canonical fields may reuse the same source column.

## Keys, duplicates, coverage and units

The candidate business key is `(state, district, market, commodity, variety, grade, parsed date)`. Variety and grade may be unknown (JSON null), but unknown categories never merge with known ones. Rows missing state, district, market, commodity or a parseable date are counted and excluded from candidate key checks. Series coverage excludes missing essential identity but counts their presence separately. Within identifiable series, invalid dates are retained as flagged rows.

An exact duplicate means equal original header names and field strings; records beyond the first are counted, never removed. Across files with different headers/aliases, equivalent normalized records are not called exact duplicates. They can still repeat a candidate business key. A conflict means that key repeats with differing original prices, arrivals, effective units, or generic Unit. Even numeric strings `150` and `150.0` remain distinguishable for conflict review.

For every identifiable series, the local coverage table reports all rows, unique parsed observation dates, first/last date, inclusive calendar span, coverage ratio, missing calendar days inside that span, gap interval count and longest gap. The first ten gap intervals are included per series. Multiple rows on one date count as one observation day. No missing dates are generated, zero-filled or imputed. Leading/trailing dates outside the observed span are not inferred. Closures and non-reporting may explain gaps.

Positive modal observation days count unique dates with positive parsed modal values and no detected price-order violation; other quality flags are reported separately and can still disqualify a series. Order checks need all three parsed prices. Missing/unparseable prices make the order check uncheckable; they do not count as passing. Nonpositive prices are counted per price column.

Units come from an explicit row-level unit field or an import-time declaration confirmed by the user. Disagreement between a row's unit and that declaration is flagged. Multiple units within a series are flagged. Generic Unit remains unassigned, and missing/unknown/unverified units remain unresolved. A header mentioning a denomination helps a human verify units; the tools do not silently assign it.

## Future prediction target and features

`modal_price` is the proposed future target once the source semantics, denomination, publication timing and usable history are confirmed. The [official AGMARKNET data-entry SOP](https://www.agmarknet.gov.in/DailyDataEntry/Docs/SOP_DEO.pdf) describes modal price through the most frequently traded price. It must not be replaced by `(min_price + max_price) / 2`; it is not necessarily an arithmetic mean.

Future features may include previously published prices, lagged rolling statistics computed only from past observations, and calendar information known at forecast time. Lagged arrivals may be considered if present, with their actual publication delay accounted for. Missing calendar days and reporting delays will affect lag definitions and must be addressed explicitly on later days.

Same-day or future minimum/maximum prices are not available inputs for predicting that day's modal price before trading/reporting. Likewise, same-day arrivals are unavailable unless their publication timing is demonstrably earlier than the prediction cutoff. Train/validation splits and features must respect that cutoff.

Weather, rainfall, soil, transport costs and production are only possible future enrichments. Each would require a separate real source, units, date/location matching, publication timing and a documented join. None is present or generated by these Day 2 tools.

## Observed Gujarat profile

The profile is restricted to Gujarat and exact Onion/Potato/Tomato labels. Full input row counts and Gujarat-wide commodity/date counts are reported separately before this filter. Quality metrics and all 229 detailed series refer to the filtered 39,634 rows. Import/profile reads are chunked; no full national dataframe is created for the default project scope. A caller explicitly choosing `--all-records` is responsible for enough memory.

The raw profile retains known price flags and one exact duplicate. Grade labels remain separate even when their observed periods differ; FAQ is never silently replaced by Non-FAQ. The shorter-history recommendation records its departure from the original 700-day target.

## Day 3 canonical cleaned observations

`data/processed/market_prices_clean.csv` uses `date`, the six series fields above, `min_price`, `modal_price`, `max_price`, `price_unit`, `source_sha256`, and `source_record`, in that order. Dates use ISO syntax. Valid price strings preserve exact decimal values; consumers should parse them numerically. `source_record` is the one-based CSV record number including the header (not a physical line number), and the hash identifies the immutable source bundle. `Commodity_Code` stays available in that original source and in rejected-row audit payloads; no arrivals are added.

Unlike the permissive raw profiler, cleaning requires all six identity columns and rejects missing identity values, including unknown variety/grade. Only whitespace is normalized in categories. Prices must be finite decimals satisfying `0 < min_price <= modal_price <= max_price`; the source-declared unit must be INR/quintal without conflicting row units. Rejected rows retain original field strings in `raw_values` within the ignored local audit. Candidate-key conflicts are quarantined before duplicate removal, including otherwise-valid siblings. Exact copies keep the lowest source hash/record; nonconflicting equivalent keys keep one deterministic copy and are counted separately. No calendar rows, corrected prices, feature columns or forecasts are created. See [Day 3](DAY_03.md).
