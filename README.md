# AiPro

Safe-by-default multi-asset trading foundation.

## Execution flow

`run.py -> telegram.py -> main.py -> TradingApplication`

The execution flow remains unchanged while asset-specific code is separated behind domain packages.

## Domain layout

```text
aipro/
├── core/        # asset-neutral models and safety boundaries
├── crypto/      # crypto configuration, adapters, and strategies
└── us_stocks/   # US-stock configuration, adapters, and strategies
```

Current state:

- Crypto domain: enabled for PAPER development; live order submission disabled.
- US-stock domain: disabled; only the isolated capital policy and package boundary exist.
- Default future US-stock capital policy: KRW 200,000 budget, 5% reserve, maximum three positions.
- Crypto and US-stock capital, brokers, state, strategies, and live approvals must remain isolated.

Legacy root modules are still used by the crypto PAPER runtime and will be migrated into `aipro/crypto/` incrementally to avoid breaking restart compatibility.

## Included

- PAPER mode by default
- Explicit double guard for LIVE mode
- Deterministic market-data adapter for offline smoke tests
- Baseline momentum strategy
- Position sizing and persistent daily-loss HALT latch
- KST daily baseline persistence
- Paper broker
- SQLite event and application-state storage
- Authenticated Telegram commands
- File and console logging
- Unit tests and GitHub Actions
- Explicit crypto and US-stock domain separation

## Run

Without a Telegram token, AiPro executes one console cycle:

```bash
python run.py
```

To enable Telegram polling, set both variables:

```bash
AIPRO_TELEGRAM_BOT_TOKEN=<bot-token>
AIPRO_TELEGRAM_ALLOWED_CHAT_IDS=<numeric-chat-id>
python run.py
```

Multiple chat IDs may be comma-separated. Never commit the bot token to GitHub.

Supported commands:

- `/status` — inspect mode, HALTED state, KST date, equity, baseline, and positions
- `/run_once` — execute one PAPER cycle when not HALTED
- `/go` — explicitly clear HALTED and rebase the daily baseline
- `/help` — show commands

Unknown or unauthorized chat IDs cannot execute commands. `/go` does not alter the baseline when the application is already ready.

## Test

```bash
python -m pytest -q
```

## Safety

This repository does not send real orders. A real Upbit adapter and a separate US-stock broker adapter, authenticated API clients, secret management, reconciliation, idempotency, retry policy, market-specific paper validation, and explicit live approval must be completed before either domain can submit LIVE orders.
