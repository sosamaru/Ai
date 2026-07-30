# Supervised Snapshot Comparison Runner

This command compares the latest immutable Upbit read-only snapshot with an explicit PAPER observation JSON file.

It does not read strategy state directly, does not mutate PAPER state, and does not submit or cancel orders.

## Required environment

```text
AIPRO_UPBIT_SNAPSHOT_COMPARE=YES
AIPRO_UPBIT_SNAPSHOT_DB=/protected/path/upbit_snapshots.sqlite3
AIPRO_PAPER_OBSERVATION_JSON=/protected/path/paper_observation.json
AIPRO_UPBIT_COMPARISON_DB=/protected/path/comparison_evidence.sqlite3
```

Optional maximum snapshot age:

```text
AIPRO_UPBIT_SNAPSHOT_MAX_AGE_SEC=300
```

## PAPER observation schema

```json
{
  "observed_at_utc": "2026-07-19T02:30:00+00:00",
  "balances": {
    "KRW": "1000000",
    "BTC": "0.01"
  },
  "open_order_ids": []
}
```

Balances are quantities, not market values. Timestamps must be timezone-aware. Currency and order identifiers must be unique.

## Run

```bash
python -m aipro.crypto.run_snapshot_comparison
```

The console report contains only status, counts, database IDs, age, and the evidence fingerprint. Full balances remain in the protected local files.

## Safety boundary

- Exchange snapshots remain immutable.
- Comparison evidence is append-only.
- PAPER cash, positions, orders, baselines, strategies, and approval state are never replaced.
- `STALE` and all validation failures fail closed.
- No authenticated mutation endpoint is present.
