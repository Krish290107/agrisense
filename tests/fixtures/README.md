# Synthetic verification fixture only

`synthetic_mandi.csv` contains eight invented rows for software tests. The market,
districts, variety, dates, and values are test inputs, not collected observations.
It deliberately includes duplicates, conflicts, missing optional fields, a bad
date, a bad number, a nonpositive price and a price-order violation.

Never import this file into `data/raw/`, use it for scope selection, present its
statistics as real coverage, or use it for model training. Tests copy it to a
temporary directory outside the real data workflow and discard that directory.
