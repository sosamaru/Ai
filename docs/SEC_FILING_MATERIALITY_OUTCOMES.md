# SEC filing materiality and historical outcomes

This construction stage extends the existing read-only SEC EDGAR metadata foundation with bounded filing-document analysis. It remains U.S.-stock PAPER intelligence and does not create trading authority.

## Inputs

- An existing normalized `SecFilingEvent`
- The public filing HTML from `https://www.sec.gov/Archives/`
- SEC Company Facts JSON for the same CIK
- Optional externally supplied price and benchmark observations

The network client requires an identifying SEC User-Agent, accepts only canonical SEC endpoints, enforces a response-size ceiling, and performs GET-only reads.

## Filing text

Visible HTML text is extracted with the Python standard library. Script, style, noscript, and SVG content is ignored. Whitespace is normalized, output size is bounded, 8-K item numbers are detected, reviewed risk phrases are recorded, and the normalized evidence receives a deterministic SHA-256 fingerprint.

The text result is research evidence. It is not an instruction source and is never interpreted as executable content.

## XBRL Company Facts

Numeric Company Facts records are normalized by taxonomy, concept, unit, period, form, accession number, and fiscal metadata. Current facts must match both the filing accession number and form. Previous-period facts are selected deterministically from earlier 10-K or 10-Q evidence with the same taxonomy, concept, and unit.

The extractor calculates:

- Period-over-period change ratio when the prior value is non-zero
- Positive-to-negative or negative-to-positive sign reversal
- Exact current and prior evidence periods
- Deterministic current-fact and comparison fingerprints

CIK mismatch, malformed facts, non-finite values, excessive current facts, and missing Company Facts structure fail closed.

## Materiality assessment

The score is a deterministic heuristic from 0 to 100. It combines:

- Reviewed form weights
- Reviewed 8-K item weights
- Distinct risk and corporate-action phrases
- Large changes or sign reversals in material financial concepts

Levels are `low`, `moderate`, `high`, and `critical`. Every contribution is included in the reason evidence. This is a research-prioritization score, not a recommendation, profitability forecast, or automatic strategy signal.

## Historical outcomes

The evaluator starts at the first supplied price observation at or after the filing timestamp. It calculates raw returns over reviewed observation horizons. When timestamp-aligned benchmark prices are supplied, benchmark and abnormal returns are also calculated.

Missing forward prices, unaligned benchmark timestamps, duplicate timestamps, invalid prices, and invalid horizons return ineligible evidence or fail closed. No market-data API is contacted by the evaluator.

## Safety boundary

A completed report:

- is PAPER-only;
- does not contact a broker;
- does not submit, cancel, replace, or retry orders;
- does not change champion state;
- does not enable LIVE mode;
- does not bypass authorization, reconciliation, portfolio risk, HALTED, or kill-switch controls;
- preserves `run.py -> telegram.py -> main.py -> TradingApplication`.

Real-time SEC ingestion, production text storage, model training from filings, and any strategy integration require separate reviewed stages and immutable validation evidence.
