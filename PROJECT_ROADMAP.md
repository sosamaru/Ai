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

Overall completion: **43%**

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
- [x] Client order ID uniqueness enforced by SQLite
- [x] Explicit order side and lifecycle status models
- [x] Validated and persisted order-state transitions
- [x] Duplicate, terminal-state, and unknown-order tests

### In progress

- [ ] Application-level forced-liquidation coverage CI repair
- [ ] Connect order lifecycle to paper-broker execution
- [ ] Position/order reconciliation
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
7. Reusing a `client_order_id` is rejected atomically by SQLite.
8. Orders follow explicit `CREATED -> SUBMITTED -> terminal` transitions.
9. Terminal orders cannot be reopened or resubmitted.
10. Telegram is disabled when no token is configured; console mode runs one cycle.
11. Unauthorized chat IDs cannot inspect or change application state.
12. Real exchange orders remain unimplemented and disabled.

## Current gaps and risks

1. Paper-broker buy and sell methods are not yet wired to the new order records.
2. Position and order reconciliation is not implemented.
3. Broker operations do not implement bounded retries, timeout handling, or partial fills.
4. The forced-liquidation application test branch still requires a successful CI result.
5. Telegram bot tokens remain environment-managed; a production secret manager is not integrated.
6. The application still uses demo market data and a paper broker only.
7. The three-step live approval flow is intentionally not implemented yet.

## Immediate priority

### P0 — Stabilize safety tests

- Repair and confirm forced-liquidation restart CI.
- Verify no previous tests regress.

### P1 — Complete order safety foundation

- Connect paper buy and sell execution to `client_order_id` records.
- Ensure duplicate executions cannot mutate cash or positions twice.
- Record failure states without losing the original order intent.
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

Confirm CI for the order lifecycle, then wire `client_order_id` into paper-broker buy and sell execution so duplicate requests cannot change account state twice.
