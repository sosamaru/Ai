# Offline Operational Readiness Export

This workflow creates a deterministic ZIP package from the latest append-only operational readiness review.

## Purpose

The package is for independent offline inspection. It contains:

- `manifest.json` — export format, creation timestamp, review fingerprint, content hash, status, and an explicit `execution_authority: false` marker
- `readiness_review.json` — canonical machine-readable review payload
- `readiness_review.md` — human-readable evidence summary, blockers, source fingerprints, and safety boundary

The ZIP uses fixed entry timestamps and sorted filenames so the same review and creation timestamp produce identical bytes.

## Explicit execution

Set:

```text
AIPRO_EXPORT_READINESS=YES
AIPRO_READINESS_REVIEW_DB=data/operational_readiness_reviews.sqlite3
AIPRO_READINESS_EXPORT_PATH=data/operational_readiness_export.zip
```

Run:

```text
python -m aipro.core.offline_readiness_export
```

Without the exact opt-in value, the command exits without exporting.

## Verification behavior

The exporter:

1. loads only the latest readiness review;
2. recalculates its canonical SHA-256 fingerprint;
3. rejects missing, malformed, or tampered evidence;
4. accepts only `NOT_READY` or `READY_FOR_INDEPENDENT_REVIEW`;
5. emits no credentials, OTP values, TOTP secrets, recipient addresses, order instructions, or authorization leases;
6. preserves source fingerprints for traceability.

## Safety boundary

The archive does not enable LIVE mode, submit orders, grant authorization, change HALTED or kill-switch state, mutate a model champion, establish profitability, or replace an independent reviewer. `READY_FOR_INDEPENDENT_REVIEW` means only that the configured evidence bundle is complete enough to be reviewed.
