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

Overall completion: **62%**

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
- [x] GitHub Actions pytest workflow with diagnostic log artifact
- [x] Persistent paper cash, positions, average prices, and order IDs
- [x] Safe recovery from invalid persisted paper-account state
- [x] Application-level forced-liquidation restart coverage
- [x] Immutable and idempotent paper order records
- [x] Deterministic application order IDs and interrupted-cycle recovery
- [x] Read-only cash and position-quantity reconciliation
- [x] Bounded retry policy, permanent-error handling, and operation deadline
- [x] Extended order states: pending, partial, rejected, cancelled, and timeout
- [x] Successful GitHub Actions validation for broker reliability
- [x] Deterministic historical replay ordered by timestamp and symbol
- [x] Configurable fees, slippage, position sizing, and maximum positions
- [x] Equity curve, total return, maximum drawdown, win rate, fees, and exposure metrics
- [x] Machine-readable and human-readable backtest reports

### In progress

- [ ] Confirm GitHub Actions for deterministic backtesting
- [ ] CSV historical-data loader and schema validation
- [ ] Paper-trading readiness criteria and validation report
- [ ] Completed-order retention and archival policy

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

1. KST date, daily baseline, HALTED state, account state, orders, and active cycle survive restarts.
2. Duplicate client order IDs cannot apply the same paper fill twice.
3. Reconciliation reconstructs expected cash and quantities and never silently edits state.
4. Transient broker failures are retried only within a bounded attempt and deadline policy.
5. Permanent broker failures are never retried.
6. Backtests sort input deterministically and therefore return the same result for the same data and configuration.
7. Backtests model buy/sell slippage and fees rather than reporting frictionless results by default.
8. Backtest reports include chronology, equity, return, drawdown, win rate, total fees, and average exposure.
9. Real exchange authentication and order submission remain unimplemented and disabled.

## Current gaps and risks

1. Historical data still must be supplied as validated `BacktestBar` objects; CSV ingestion is not implemented yet.
2. The current backtest fills at the supplied bar price adjusted by fixed slippage and does not model order-book depth or partial fills.
3. Open positions are marked to the latest supplied price at the end of a backtest rather than forcibly liquidated.
4. The reliability executor is intentionally not wired into `PaperBroker`; local paper operations are synchronous and deterministic.
5. A real exchange adapter must reconcile an order ID after timeout before submitting it again.
6. Completed order history needs retention limits before long-running operation.
7. The application still uses demo market data and a paper broker only.

## Immediate priority

### P0 — Validate deterministic backtesting

- Confirm GitHub Actions passes all new replay and metric tests.
- Verify input ordering does not change results.
- Verify fees and slippage reduce returns as expected.

### P1 — Historical data ingestion

- Add strict CSV parsing with timestamp, symbol, price, momentum, and volatility validation.
- Reject duplicate or malformed rows before a backtest starts.
- Add dataset metadata and reproducibility fingerprinting.

### P2 — Paper-trading acceptance gate

- Define minimum sample size, maximum drawdown, fee-adjusted return, and stability requirements.
- Produce a pass/fail readiness report without enabling live trading.
- Require multiple market regimes and out-of-sample validation.

### P3 — Exchange-readiness

- Add read-only Upbit market data first.
- Apply HTTP connect/read timeouts at the adapter boundary.
- Keep authenticated order submission disabled until readiness criteria pass.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, and next priority are all recorded.

## Next action

Confirm CI for deterministic backtesting, then add validated historical-data ingestion and a measurable paper-trading readiness gate before any authenticated exchange integration.
