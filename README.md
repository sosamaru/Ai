# AiPro

Safe-by-default automated crypto trading project.

## Execution flow

`run.py -> telegram.py -> main.py -> TradingApplication`

This path is an architecture contract. New features must be connected through `TradingApplication` rather than creating a second startup path.

## Current capability

- PAPER mode by default
- Explicit double guard for LIVE mode
- Deterministic market-data adapter for offline smoke tests
- Baseline momentum strategy
- Position sizing and daily-loss HALT behavior
- Paper broker
- SQLite event log
- File and console logging
- Unit tests and GitHub Actions CI

The detailed completion state, missing components, risks, and next priorities are tracked in `PROJECT_ROADMAP.md`.

## Setup

```bash
python -m venv .venv
```

Activate the environment, install pytest for development, and copy the environment template:

```bash
python -m pip install --upgrade pip pytest
cp .env.example .env
```

On Windows PowerShell, use:

```powershell
Copy-Item .env.example .env
```

## Run

```bash
python run.py
```

## Test

```bash
python -m compileall -q .
python -m pytest -q
```

## Development order

1. Read `PROJECT_ROADMAP.md` and this README.
2. Confirm the existing code path and interfaces before implementing a feature.
3. Keep exchange actions behind broker/adapter boundaries.
4. Add or update tests.
5. Run compile and test checks.
6. Update roadmap completion, gaps, remaining work, and next priority.

## Safety

This repository does not send real orders. A real Upbit adapter, authenticated API client, durable reconciliation, idempotency, bounded retry policy, partial-fill handling, persistent loss controls, and paper-trading validation must be completed before LIVE mode is considered.

Never commit `.env`, API keys, bot tokens, account identifiers, database files, or logs.