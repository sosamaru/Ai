# Operational Readiness Review Bundle

This module combines immutable operational evidence into one fail-closed review bundle.

It reads the latest evidence from:

- supervised SMTP delivery verification
- supervised TOTP verification
- Alpaca PAPER readiness reports
- append-only operator attestations for mailbox arrival, offline TOTP recovery storage, and supervised Upbit preflight

The result is either:

- `NOT_READY`
- `READY_FOR_INDEPENDENT_REVIEW`

`READY_FOR_INDEPENDENT_REVIEW` is deliberately not `LIVE_READY`. It does not enable LIVE mode, create an authorization lease, submit an order, change a champion, or bypass any risk or reconciliation gate. A separate human review and future explicitly approved real-order implementation remain mandatory.

## Manual attestations

Manual facts that source code cannot prove are recorded as hashes in an append-only SQLite database. The allowed attestation kinds are:

- `mailbox_arrival_confirmed`
- `totp_recovery_stored_offline`
- `upbit_preflight_supervised`

The operator label and note are hashed before persistence. Secrets, TOTP recovery material, mailbox contents, and credentials must never be placed in the note.

## Fail-closed behavior

Missing databases, missing tables, absent successful evidence, a non-qualifying PAPER report, or any missing attestation produce `NOT_READY` with explicit blockers. Source evidence fingerprints are carried into the review so the decision can be traced without copying sensitive payloads.

## Operational boundary

Synthetic test fixtures verify code behavior only. They do not satisfy SMTP delivery, mailbox arrival, TOTP enrollment, offline recovery storage, Upbit supervised preflight, or the real 30-calendar-day Alpaca PAPER requirement.
