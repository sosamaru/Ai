# SEC EDGAR filing intelligence

## Scope

AiPro reads the SEC submissions JSON endpoint and converts recent public filings into deterministic, broker-neutral PAPER intelligence events.

## Included

- mandatory descriptive User-Agent with contact email
- zero-padded CIK validation
- read-only `data.sec.gov/submissions/CIK##########.json` access
- normalization of accession number, form, filing date, report date, primary document, filing items, and canonical SEC Archives URL
- event classes for annual and quarterly reports, material events, insider transactions, beneficial ownership, securities offerings, proxy filings, and other filings
- optional form filtering
- missing and stale filing fail-closed states
- deterministic SHA-256 event and snapshot fingerprints

## Safety boundary

The module does not submit orders, modify balances or positions, change daily baselines, authorize LIVE mode, or resume HALTED operation. Filing data remains PAPER-only evidence until separate out-of-sample strategy validation passes.

The event classification is structural and form-based. It does not claim that a filing is bullish, bearish, profitable, or predictive. Filing text extraction, XBRL facts, materiality scoring, and historical outcome evaluation remain future work.

## Operational rules

Use a truthful SEC User-Agent containing the application name and a monitored contact email. Apply the existing resilience layer for rate limiting, bounded retries, circuit breaking, caching, and append-only execution evidence. Secrets are not required for public SEC submissions access.
