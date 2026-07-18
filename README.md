# AiPro

Safe-by-default automated crypto trading MVP.

## Execution flow

`run.py -> telegram.py -> main.py -> TradingApplication`

## Included

- PAPER mode by default
- Explicit double guard for LIVE mode
- Deterministic market-data adapter for offline smoke tests
- Baseline momentum strategy
- Position sizing and persistent daily-loss HALT latch
- KST daily baseline persistence
- Persistent paper cash, positions, and transaction history
- SQLite event and application-state storage
- Authenticated Telegram commands
- File and console logging
- Unit tests and GitHub Actions

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

## Persistent paper account

The paper broker stores cash, positions, average prices, and transaction history in the configured SQLite database. A restarted process restores the latest paper account instead of resetting simulated capital. Use only one AiPro process per database file until multi-process locking and reconciliation are implemented.

## Test

```bash
python -m pytest -q
```

## Safety

This repository does not send real orders. A real Upbit adapter, authenticated API client,
secret management, reconciliation, idempotency, retry policy, and paper-trading validation
must be completed before LIVE mode is considered.
