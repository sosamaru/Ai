# Snapshot reconciliation evidence

This component compares an immutable Upbit read-only account snapshot with an explicitly supplied PAPER observation.

## Safety boundary

- Exchange data never replaces PAPER cash, positions, orders, daily baseline, strategy inputs, or LIVE approval state.
- Comparison results are written to a separate append-only table: `exchange_snapshot_comparison_evidence`.
- Database triggers reject UPDATE and DELETE operations.
- No order submission, cancellation, or mutation endpoint is used.

## Results

- `MATCH` — balances and open-order UUID sets match within the configured tolerance.
- `MISMATCH` — one or more balances, currencies, or open-order UUIDs differ.
- `STALE` — the exchange snapshot exceeds the configured maximum age. Staleness takes priority over content equality.

## Balance interpretation

The exchange quantity for each currency is `balance + locked`. PAPER observations must provide total quantities using the same currency keys. The default absolute tolerance is `0.00000001`.

## Evidence

Each result records:

- source snapshot ID and fingerprint
- comparison timestamp and snapshot age
- mismatched currencies
- exchange-only and PAPER-only currencies
- exchange-only and PAPER-only order UUIDs
- deterministic SHA-256 evidence fingerprint

The evidence store is intentionally separate from both the exchange snapshot table and all PAPER state tables.
