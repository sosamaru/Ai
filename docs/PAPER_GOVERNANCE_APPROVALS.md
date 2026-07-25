# PAPER Governance Approval Ledger

## Purpose

The approval ledger stores explicit operator review evidence for PAPER champion-monitoring recommendations. It separates automated monitoring from human governance decisions.

## Recorded evidence

Each append-only event records:

- crypto or US-stock domain
- monitoring decision SHA-256 fingerprint
- recommendation under review
- outcome: approve, reject, or defer
- reviewer identifier
- mandatory reason
- previous event ID for the same domain
- UTC timestamp and schema version
- PAPER-only marker
- explicit `grants_execution_authority = false` marker

## Fail-closed rules

- Blank reviewer IDs and reasons are rejected.
- Monitoring fingerprints must be lowercase SHA-256 digests.
- Non-PAPER monitoring decisions are rejected.
- `HOLD` and `ABSTAIN` cannot be approved as state-changing actions.
- The same reviewer cannot overwrite or submit a second outcome for the same monitoring decision.
- Crypto and US-stock histories are stored and verified independently.
- SQLite triggers block UPDATE and DELETE.
- Event-chain verification checks linkage, fingerprints, PAPER scope, and absence of execution authority.

## Authority boundary

An approval event is governance evidence only. It does not mutate the champion registry, activate or roll back a model, serve inference, contact a broker, submit PAPER orders, authorize LIVE mode, or bypass any risk control.

A separate reviewed command would still be required to apply an approved governance action to the champion registry. No such automatic bridge is implemented here.
