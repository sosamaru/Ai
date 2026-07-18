# AiPro Project Roadmap

Updated: 2026-07-18

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

Overall completion: **38%**

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
- [x] Persistent paper cash and positions
- [x] Immutable paper transaction history
- [x] Paper-account restoration at application startup
- [x] Corrupted paper-account state validation
- [x] Restart and forced-liquidation persistence tests

### In progress

- [ ] Confirm a successful GitHub Actions test result for persistent paper-account changes
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
4. Paper cash, positions, and transaction history survive process restarts.
5. Paper-account updates are committed atomically in SQLite.
6. Invalid negative cash or non-positive positions fail closed during restoration.
7. Forced liquidation persists the empty position state before restart.
8. Telegram is disabled when no token is configured; console mode runs one cycle.
9. A configured token without authorized chat IDs fails closed at startup.
10. Unauthorized chat IDs cannot inspect or change application state.
11. `/run_once` is rejected while HALTED.
12. `/go` only changes state when HALTED; repeated `/go` cannot silently rebase equity.
13. Telegram uses HTTPS Bot API long polling and retries transient failures.
14. Real exchange orders remain unimplemented and disabled.

## Current gaps and risks

1. Broker operations do not yet implement client order IDs, reconciliation, partial fills, or retries.
2. SQLite persistence is process-local and does not provide distributed locking for multiple application instances.
3. Telegram bot tokens remain environment-managed; a production secret manager is not integrated.
4. Telegram uses a single-process polling loop without process supervision.
5. The application still uses demo market data and a paper broker only.
6. A successful CI run for this branch has not yet been confirmed in this document.
7. The three-step live approval flow is intentionally not implemented yet.

## Immediate priority

### P0 — Verify persistent paper account

- Confirm the full pytest suite in GitHub Actions.
- Review SQLite behavior under abrupt process termination.
- Keep only one active AiPro process per database file.

### P1 — Order safety foundation

- Add idempotent client order identifiers.
- Define order states and immutable transaction records.
- Add bounded retry and timeout policies.
- Add startup reconciliation between intended orders and broker state.

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

Run the complete pytest suite in GitHub Actions, then begin the idempotent order lifecycle and reconciliation foundation without enabling real exchange orders.
