# Alpaca PAPER Readiness Evidence Runbook

This workflow collects account and order evidence from the official Alpaca PAPER domain and derives an append-only readiness report. It never contacts the live Alpaca domain and never grants live-trading authority.

## Required environment

- `AIPRO_ALPACA_PAPER_VERIFY=YES`
- `APCA_PAPER_API_KEY_ID`
- `APCA_PAPER_API_SECRET_KEY`

Optional policy settings:

- `AIPRO_ALPACA_PAPER_EVIDENCE_DB` (default `data/alpaca_paper_evidence.sqlite3`)
- `AIPRO_ALPACA_PAPER_REPORT_DB` (default `data/alpaca_paper_readiness.sqlite3`)
- `AIPRO_PAPER_MIN_DAYS` (default `30`)
- `AIPRO_PAPER_MAX_GAP_HOURS` (default `36`)
- `AIPRO_PAPER_MAX_DRAWDOWN_PCT` (default `10`)
- `AIPRO_PAPER_MIN_DISTINCT_ORDERS` (default `1`)

## Run

```bash
python scripts/verify_alpaca_paper_readiness.py
```

Schedule the command once per day in a supervised PAPER-only environment. The process exits with status `0` only when all configured PAPER evidence requirements pass. It exits with status `2` when evidence is incomplete or unhealthy.

## Fail-closed checks

The report rejects qualification when any of the following is present:

- fewer than the configured calendar days
- a missing UTC evidence date
- a capture gap above the configured threshold
- an inactive, blocked, or user-suspended PAPER account snapshot
- one `client_order_id` linked to more than one distinct Alpaca order ID
- fewer than the required distinct orders
- maximum equity drawdown above the configured threshold
- evidence timestamped in the future

A previously observed order may appear in many daily snapshots. This is normal and is not classified as duplication unless the same client order ID maps to different order IDs.

## Evidence boundary

Both raw snapshots and derived reports are protected by SQLite append-only triggers. Reports contain account and order evidence returned by Alpaca, so database files must be stored outside the repository with restricted filesystem permissions and backed up securely.

Thirty calendar days cannot be simulated or accelerated for operational approval. Test fixtures prove code behavior only. A qualifying report is necessary evidence, not a live-readiness decision, profitability guarantee, or permission to submit real orders.
