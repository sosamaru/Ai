# PAPER Intelligence Features

AiPro V1 now converts normalized news and provider-native ticker sentiment into deterministic, broker-neutral feature snapshots.

## Included

- Alpha Vantage ticker relevance, sentiment score, and label preservation
- deterministic event classification
- confidence-weighted generic sentiment fusion
- relevance-weighted provider-native sentiment aggregation
- article freshness eligibility gate
- SHA-256 snapshot fingerprint
- explicit `NO_RELEVANT_ARTICLES` and `STALE_INTELLIGENCE` fail-closed states

## Safety boundary

`PaperIntelligenceSnapshot` is data only. It cannot place orders, resume HALTED trading, alter balances, reset daily baselines, or complete LIVE approval. Strategy integration requires a separate PAPER evaluation step and new regression evidence.

## Determinism

For the same symbol, article fingerprints, sentiment observations, native observations, and `as_of_utc`, the produced snapshot and fingerprint are identical.

## V1 completion meaning

V1 foundation completion means the planned architecture, PAPER safety gates, persistence, validation, approval intent flow, provider-neutral news ingestion, resilience controls, native sentiment preservation, event classification, and deterministic PAPER feature snapshots are implemented and tested.

It does not mean profitable trading is proven, supervised operation is complete, or authenticated order submission is enabled. Those items remain in the V2 operational and research backlog.
