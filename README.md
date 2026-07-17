# AiPro

Safe-by-default automated crypto trading research platform.

## Execution flow

`run.py -> telegram.py -> main.py -> TradingApplication`

This chain is a compatibility boundary and must be preserved while the internal modules are expanded.

## Current capability

- PAPER mode by default
- Explicit multiple guards for future LIVE mode
- Deterministic market-data adapter for offline smoke tests
- Baseline momentum strategy
- Position sizing and daily-loss HALT latch
- Paper broker
- SQLite event log
- File and console logging
- Unit tests and GitHub Actions quality checks

The repository is still a research and PAPER-trading system. It must not send real orders yet. See `PROJECT_ROADMAP.md` for release gates and current completion.

## Setup

```bash
python -m venv .venv
```

Activate the environment, then install the project and development tools:

```bash
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and keep the safe defaults. Never commit `.env`.

## Run

```bash
python run.py
```

## Validate

```bash
python -m ruff check .
python -m mypy aipro
python -m pytest --cov=aipro --cov-report=term-missing
```

## Development order

1. Read `PROJECT_ROADMAP.md`, this README, and `SECURITY.md`.
2. Compare documentation with the current code before implementing a feature.
3. Preserve the execution flow and add functionality behind clear interfaces.
4. Add tests for success, failure, restart, and edge cases.
5. Update roadmap completion, gaps, remaining work, and next priority in the same pull request.

## Safety

A real Upbit order adapter, authenticated reconciliation, idempotency, bounded retries, secret management, monitoring, and extended PAPER validation are required before LIVE mode can be considered. LIVE trading is optional and profitability is never guaranteed.
