# AiPro Project Roadmap

Updated: 2026-07-17

## Project goal

Build a safe, maintainable automated crypto-trading system while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Development order:

1. Offline tests
2. Backtesting
3. Paper trading
4. Live-readiness review
5. Explicitly approved live trading

## Current status

Overall completion: **34%**

### Completed

- [x] Project package and entry-point structure
- [x] Safe configuration defaults and PAPER default
- [x] Double guard for LIVE mode
- [x] Domain models and baseline momentum strategy
- [x] Basic risk manager and paper broker
- [x] Deterministic demo market data
- [x] SQLite event and key-value state storage
- [x] Persistent KST trading date and daily baseline
- [x] Persistent HALTED latch across restarts
- [x] Explicit application-level `resume()` with equity rebasing
- [x] Safe application status snapshot
- [x] Telegram token and authorized-chat configuration
- [x] Unauthorized Telegram command rejection
- [x] `/status`, `/run_once`, `/go`, and `/help`
- [x] `/go` restricted to HALTED state
- [x] Standard-library Telegram long polling with retry
- [x] Configuration, persistent-state, and Telegram router tests
- [x] GitHub Actions pytest workflow

### In progress

- [ ] Confirm a successful GitHub Actions test result
- [ ] Application-level forced-liquidation coverage
- [ ] Persistent paper-broker cash and positions
- [ ] Position/order reconciliation
- [ ] Idempotent order lifecycle
- [ ] Retry and timeout policy for broker operations
- [ ] Backtesting engine and performance report
- [ ] Paper-trading readiness validation

### Not started

- [ ] Real Upbit read-only market-data adapter
- [ ] Authenticated Upbit account client
- [ ] `/ai_upbit_go -> /confirm -> /go` live approval flow
- [ ] News/sentiment input
- [ ] Chart-pattern features
- [ ] Market-regime detection
- [ ] EV and volatility-based sizing
- [ ] Model training and inference pipeline
- [ ] Deployment and operational monitoring

## Current behavior

1. KST date and daily baseline survive process restarts.
2. Daily-loss HALTED survives restarts and date changes.
3. Only explicit resume clears HALTED and creates a new baseline.
4. Telegram is disabled when no token is configured; console mode runs one cycle.
5. A configured token without authorized chat IDs fails closed at startup.
6. Unauthorized chat IDs cannot inspect or change application state.
7. `/run_once` is rejected while HALTED.
8. `/go` only changes state when HALTED; repeated `/go` cannot silently rebase equity.
9. Telegram uses HTTPS Bot API long polling and retries transient failures.
10. Real exchange orders remain unimplemented and disabled.

## Current gaps and risks

1. Paper broker cash and positions are still memory-only and reset after restart.
2. Telegram bot tokens remain environment-managed; a production secret manager is not integrated.
3. Telegram uses a single-process polling loop without process supervision.
4. Broker operations do not implement idempotency, reconciliation, partial fills, or retries.
5. The application still uses demo market data and a paper broker only.
6. A successful CI run has not yet been confirmed in this document.
7. The three-step live approval flow is intentionally not implemented yet.

## Immediate priority

### P0 — Persist paper account state

- Persist cash, positions, average prices, and transaction history.
- Restore paper account state at startup.
- Reconcile impossible or corrupted state safely.
- Add restart and forced-liquidation tests.

### P1 — Order safety foundation

- Add idempotent client order identifiers.
- Define order states and immutable transaction records.
- Add bounded retry and timeout policies.

### P2 — Validation foundation

- Build deterministic replay/backtesting support.
- Record fees, slippage, drawdown, win rate, and exposure.
- Define measurable paper-trading acceptance criteria.

### P3 — Exchange integration

- Implement read-only Upbit market data first.
- Add authenticated account reconciliation.
- Keep order submission disabled until readiness criteria pass.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, and next priority are all recorded.

## Next action

Persist the paper broker account and positions in SQLite so process restarts cannot reset simulated capital or bypass risk accounting.
