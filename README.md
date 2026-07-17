# AiPro

API-free, safety-first cryptocurrency trading core.

## Architecture

`run.py -> telegram.py -> main.py -> TradingApplication`

## Implemented

- PAPER mode by default
- Explicit LIVE dual lock
- Position sizing and daily loss HALT
- Fee and slippage accounting
- Duplicate order TTL guard
- Persistent SQLite event and state storage
- Restart recovery for cash, positions, controller mode, and baseline
- RUNNING / PAUSED / HALTED controller
- Offline command processor: `/status`, `/pause`, `/resume`, `/halt`, `/go`
- KST daily session rollover helper
- Deterministic backtest engine and performance metrics
- Exchange protocol with a fake adapter for integration tests
- GitHub Actions compilation and pytest checks

## Safety boundary

No exchange or Telegram secret is stored in the repository. Real network adapters are connected only after all API-free tests pass and credentials are supplied through environment variables or GitHub/VPS secrets.

## Test

```bash
python -m pip install pytest
python -m compileall -q .
python -m pytest -q
```

## Required credentials for the final integration stage

```env
UPBIT_ACCESS_KEY=
UPBIT_SECRET_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Never commit real values to Git.
