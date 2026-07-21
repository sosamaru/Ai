# FRED macro intelligence

## Scope

AiPro now has a broker-neutral FRED adapter and deterministic PAPER-only macro snapshot.

The first required series are:

- `CPIAUCSL` — consumer price index level
- `DFF` — effective federal funds rate
- `UNRATE` — unemployment rate

## Safety boundary

Macro observations are intelligence data only. They cannot submit orders, change balances or positions, reset daily baselines, resume HALTED state, or bypass authorization and readiness gates.

A snapshot fails closed when a required series is missing or older than the configured maximum age. The result includes an explicit eligibility flag, reason, regime, score, and SHA-256 fingerprint.

## Current limitation

The initial regime score is a transparent deterministic baseline, not a trained profitability model. It must be evaluated against historical out-of-sample data before it can influence PAPER position sizing.

## Next development step

Add SEC EDGAR filing-event normalization, then combine news, macro, filings, chart, volatility, and liquidity features in a versioned PAPER feature vector. Real-order integration remains prohibited until separate operational evidence and live-readiness review pass.
