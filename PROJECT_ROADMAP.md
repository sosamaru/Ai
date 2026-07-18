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
- [x] Persistent paper cash, positions, and average prices
- [x] Safe recovery from invalid persisted paper-account state
- [x] Immutable paper buy/sell event records in SQLite
- [x] Paper-account restart, liquidation, corruption, and invalid-trade tests

### In progress

- [ ] Confirm a successful GitHub Actions test result for the persistence branch
- [ ] Application-level forced-liquidation coverage
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
4. Paper cash, positions, and average prices survive process restarts.
5. Invalid or corrupted paper-account state is rejected and safely reinitialized.
6. Every successful paper buy and sell writes an immutable event record.
7. Telegram is disabled when no token is configured; console mode runs one cycle.
8. A configured token without authorized chat IDs fails closed at startup.
9. Unauthorized chat IDs cannot inspect or change application state.
10. `/run_once` is rejected while HALTED.
11. `/go` only changes state when HALTED; repeated `/go` cannot silently rebase equity.
12. Telegram uses HTTPS Bot API long polling and retries transient failures.
13. Real exchange orders remain unimplemented and disabled.

## Current gaps and risks

1. Broker operations still lack idempotent client order identifiers and explicit order states.
2. Position and order reconciliation is not implemented.
3. Telegram bot tokens remain environment-managed; a production secret manager is not integrated.
4. Telegram uses a single-process polling loop without process supervision.
5. Broker operations do not implement bounded retries, timeout handling, or partial fills.
6. The application still uses demo market data and a paper broker only.
7. The persistence branch still requires a confirmed successful CI run.
8. The three-step live approval flow is intentionally not implemented yet.

## Immediate priority

### P0 — Complete persistence validation

- Confirm GitHub Actions passes on the persistence branch.
- Add application-level forced-liquidation restart coverage.
- Verify no previous tests regress.

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

Confirm CI for persistent paper-account state, then add application-level forced-liquidation restart coverage before starting the idempotent order lifecycle.
