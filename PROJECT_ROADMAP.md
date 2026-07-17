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

Overall completion: **18%**

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
- [x] Logging configuration
- [x] Initial `TradingApplication` cycle

### In progress

- [ ] Configuration validation test coverage
- [ ] Application-level test coverage
- [ ] Persistent daily baseline and KST reset
- [ ] Persistent HALTED latch and explicit resume flow
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

## Current gaps and risks

1. The current daily baseline exists only in memory and does not reset at 00:00 KST.
2. HALTED state is not persisted, so a process restart can bypass the latch.
3. The application uses demo market data and a paper broker only.
4. Broker operations do not yet implement idempotency, reconciliation, partial fills, or retries.
5. Telegram is currently an entry layer, not a secured control plane.
6. Test coverage is incomplete and no CI result is currently recorded here.

## Immediate priority

### P0 — Safety foundation

- Add strict configuration tests.
- Persist baseline, trading date, and HALTED state.
- Require explicit resume after a daily-loss halt.
- Add application tests for forced liquidation and halt behavior.

### P1 — Validation foundation

- Build deterministic replay/backtesting support.
- Record fees, slippage, drawdown, win rate, and exposure.
- Define paper-trading acceptance criteria.

### P2 — Exchange integration

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

Implement and test persistent KST daily baseline and HALTED latch without changing the existing entry-point structure.
