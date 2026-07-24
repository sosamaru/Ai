# Immutable PAPER Champion Registry

AiPro records model-champion activation, replacement, rollback, and deactivation as append-only PAPER governance evidence.

## Recorded evidence

Each event contains:

- crypto or US-stock domain
- action type
- candidate name and evaluation fingerprint
- champion-decision fingerprint
- previous event ID
- mandatory human-readable reason
- UTC timestamp
- schema version and PAPER-only marker
- deterministic SHA-256 event ID

## Integrity rules

- Crypto and US-stock histories are queried and changed independently.
- Only an approved champion decision may be activated.
- Re-activating the current candidate is rejected.
- Rollback targets must exist in the same domain.
- Every new event links to the immediately previous event in its domain.
- Concurrent changes fail closed when the expected previous event no longer matches.
- SQLite triggers reject UPDATE and DELETE operations.
- Deactivation adds a new event instead of deleting history.
- Chain verification recomputes event fingerprints and previous-event links.

## Safety boundary

The registry stores governance evidence only. It does not persist model binaries, load models, generate predictions, train candidates, contact brokers, create orders, enable LIVE mode, bypass authorization, override HALTED state, or bypass portfolio-risk and readiness gates.

A registered PAPER champion remains a research artifact until independent domain-specific PAPER evidence, drift monitoring, cost-aware expected value, portfolio controls, reconciliation, and every mandatory safety gate pass.