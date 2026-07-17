# AiPro Project Roadmap

Updated: 2026-07-17

## Project goal

Build a safe, maintainable automated crypto-trading system while preserving the execution path:

`run.py -> telegram.py -> main.py -> TradingApplication`

Development must proceed in this order:

1. Offline tests
2. Backtesting
3. Paper trading
4. Live-trading readiness review
5. Explicitly approved live trading

## Current status

Overall completion: **26%**

### Completed

- [x] Project package and entry-point structure
- [x] Safe configuration defaults
- [x] PAPER mode as default
- [x] Double guard for LIVE mode
- [x] Domain models
- [x] Baseline momentum strategy
- [x] Basic risk manager
- [x] Paper broker
- [x] Deterministic demo market data
- [x] SQLite event storage
- [x] Persistent key-value application state storage
- [x] Logging configuration
- [x] Initial `TradingApplication` cycle
- [x] Configuration validation tests
- [x] Persistent KST trading date and daily baseline
- [x] Persistent HALTED latch across process restarts
- [x] Explicit application-level `resume()` with equity rebasing
- [x] Automated GitHub Actions pytest workflow

### In progress

- [ ] Confirm the first GitHub Actions test result
- [ ] Application-level forced-liquidation coverage
- [ ] Secure Telegram resume command
- [ ] Position/order reconciliation
- [ ] Idempotent order lifecycle
- [ ] Retry and timeout policy
- [ ] Backtesting engine and performance report
- [ ] Paper-trading readiness validation

### Not started

- [ ] Real Upbit market-data adapter
- [ ] Authenticated Upbit client
- [ ] Telegram command authorization
- [ ] `/ai_upbit_go -> /confirm -> /go` approval flow
- [ ] News/sentiment input
- [ ] Chart-pattern features
- [ ] Market-regime detection
- [ ] EV and volatility-based sizing
- [ ] Model training and inference pipeline
- [ ] Deployment and operational monitoring

## Current behavior

1. The application derives its trading date from `Asia/Seoul`.
2. The first cycle of a KST date stores the current equity as that day's baseline.
3. A daily-loss breach persists `halted=1` in SQLite.
4. Restarting the process does not clear HALTED.
5. A KST date change resets the baseline but does not automatically clear HALTED.
6. Only an explicit `TradingApplication.resume()` clears the latch and creates a new baseline.
7. Missing prices prevent unsafe forced liquidation of that symbol and produce an error log.

## Current gaps and risks

1. `resume()` exists at application level but is not yet exposed through an authenticated Telegram command.
2. The paper broker state itself is not persisted, so cash and positions still reset after restart.
3. Broker operations do not yet implement idempotency, reconciliation, partial fills, or retries.
4. The application still uses demo market data and a paper broker only.
5. Telegram is currently an entry layer, not a secured control plane.
6. The newly added GitHub Actions workflow has not yet produced a recorded run result.

## Immediate priority

### P0 — Complete safety control plane

- Confirm CI passes all configuration and persistent-state tests.
- Add forced-liquidation application tests.
- Add authorized Telegram status and resume commands.
- Prevent any unauthenticated command from clearing HALTED.

### P1 — Persist paper-trading account state

- Persist cash, positions, average prices, and transaction history.
- Reconcile persisted positions at startup.
- Add idempotent client order identifiers.

### P2 — Validation foundation

- Build deterministic replay/backtesting support.
- Record fees, slippage, drawdown, win rate, and exposure.
- Define measurable paper-trading acceptance criteria.

### P3 — Exchange integration

- Implement read-only Upbit market data first.
- Add authenticated account reconciliation.
- Keep order submission disabled until readiness criteria pass.

## Completion policy

A task is complete only when:

- implementation is committed,
- automated tests are added and pass,
- documentation matches the code,
- remaining limitations are recorded,
- the next priority is identified.

## Next action

Confirm CI, then implement an authenticated Telegram control plane for status inspection and explicit HALTED resume without changing the existing entry-point structure.
