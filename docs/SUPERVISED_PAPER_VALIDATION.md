# Supervised Crypto PAPER Validation

This phase records deterministic evidence that the crypto PAPER runtime behaved safely during a supervised observation period.

## Scope

The validator evaluates only supplied observation facts. It does not start the runtime, submit orders, enable LIVE mode, change balances, or modify strategy state.

Evidence includes:

- historical dataset SHA-256 fingerprint
- strategy and configuration versions
- observation start and end timestamps
- completed cycle count
- restart recovery evidence
- HALTED-path evidence
- provider failure count
- stale source timestamp count
- duplicate order ID count
- unhandled exception count

## Default PASS gates

A result is `PASS` only when all of these conditions are true:

- at least 24 completed cycles
- at least one verified restart recovery
- at least one verified HALTED-path event
- zero provider failures
- zero stale source events
- zero duplicate order IDs
- zero unhandled exceptions

Any failed or missing safety condition produces `FAIL`.

## Immutable evidence

`PaperValidationEvidenceStore` writes results to the dedicated `crypto_paper_validation_evidence` table.

- rows are append-only
- SHA-256 fingerprints are unique
- database triggers reject UPDATE and DELETE
- the table is isolated from PAPER cash, positions, orders, baselines, strategies, exchange snapshots, and LIVE approval state

A `PASS` report is evidence for later readiness review only. It does not authorize LIVE trading.
