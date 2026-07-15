# AiPro

Safe-by-default automated crypto trading MVP.

## Execution flow

`run.py -> telegram.py -> main.py -> TradingApplication`

## Included

- PAPER mode by default
- Explicit double guard for LIVE mode
- Deterministic market-data adapter for offline smoke tests
- Baseline momentum strategy
- Position sizing and daily-loss HALT latch
- Paper broker
- SQLite event log
- File and console logging
- Unit tests

## Run

```bash
python run.py
```

## Test

```bash
python -m pytest -q
```

## Safety

This repository does not send real orders. A real Upbit adapter, authenticated API client,
secret management, reconciliation, idempotency, retry policy, and paper-trading validation
must be completed before LIVE mode is considered.
