# AiPro Project Roadmap

Updated: 2026-07-18

## Project goal

Build a safe, maintainable multi-asset automated trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains are isolated as:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies

Development order:

1. Offline tests
2. Backtesting
3. Paper trading
4. Live-readiness review
5. Explicitly approved live trading

Each asset domain must pass this sequence independently. Capital, broker state, risk limits, order IDs, approval state, and credentials must never be shared implicitly between crypto and US stocks.

## Current status

Overall completion: **64%**

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
- [x] Explicit shared-core, crypto, and US-stock package boundaries
- [x] Disabled-by-default US-stock domain with isolated KRW 200,000 capital policy
- [x] Domain tests preventing disabled assets from enabling live order submission

### In progress

- [ ] Migrate legacy crypto runtime modules from `aipro/` into `aipro/crypto/` without breaking persisted state
- [ ] Confirm GitHub Actions for deterministic backtesting and domain separation
- [ ] CSV historical-data loader and schema validation
- [ ] Paper-trading readiness criteria and validation report
- [ ] Completed-order retention and archival policy

### Not started

#### Crypto

- [ ] Real Upbit read-only market-data adapter
- [ ] Authenticated Upbit account client
- [ ] `/ai_upbit_go -> /confirm -> /go` live approval flow

#### US stocks

- [ ] Select and implement a read-only US-stock market-data adapter
- [ ] Select a supported broker and build PAPER adapter
- [ ] US momentum/gap scanner and liquidity filters
- [ ] Separate USD cash, positions, orders, database namespace, and approval flow
- [ ] US-market-hours and holiday calendar handling
- [ ] US-stock-specific backtesting and paper-readiness gate

#### Shared intelligence

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
9. The active runtime remains crypto PAPER only.
10. The US-stock domain is present but disabled and cannot submit orders.
11. The default US-stock policy reserves 5% of its KRW 200,000 allocation and permits at most three positions.
12. Real exchange authentication and order submission remain unimplemented and disabled for both domains.

## Current gaps and risks

1. Legacy crypto runtime modules still live directly under `aipro/`; moving them requires compatibility imports and persistence regression tests.
2. Historical data still must be supplied as validated `BacktestBar` objects; CSV ingestion is not implemented yet.
3. The current backtest fills at the supplied bar price adjusted by fixed slippage and does not model order-book depth or partial fills.
4. Open positions are marked to the latest supplied price at the end of a backtest rather than forcibly liquidated.
5. The reliability executor is intentionally not wired into `PaperBroker`; local paper operations are synchronous and deterministic.
6. A real exchange adapter must reconcile an order ID after timeout before submitting it again.
7. Completed order history needs retention limits before long-running operation.
8. US-stock broker, market data, market calendar, FX accounting, taxes, and fractional-share behavior are not implemented.
9. The application still uses demo market data and a paper broker only.

## Immediate priority

### P0 — Validate separation safely

- Confirm all existing tests and new asset-domain tests pass.
- Verify the execution flow remains unchanged.
- Add compatibility imports before physically moving legacy crypto modules.

### P1 — Complete crypto module migration

- Move crypto market, strategy, broker wiring, and settings ownership into `aipro/crypto/`.
- Keep shared models, storage contracts, reliability, and generic backtesting in `aipro/core/` or asset-neutral modules.
- Preserve existing SQLite state keys and deterministic order IDs.

### P2 — Historical data ingestion

- Add strict CSV parsing with timestamp, symbol, price, momentum, and volatility validation.
- Reject duplicate or malformed rows before a backtest starts.
- Add dataset metadata and reproducibility fingerprinting.

### P3 — Independent paper-readiness gates

- Define minimum sample size, maximum drawdown, fee-adjusted return, and stability requirements.
- Produce separate pass/fail reports for crypto and US stocks.
- Require multiple market regimes and out-of-sample validation.

### P4 — Exchange-readiness

- Add read-only Upbit market data first.
- Research and select a compliant US-stock broker/data interface before implementation.
- Keep authenticated order submission disabled until each domain's readiness criteria pass.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, and next priority are all recorded.

## Next action

Confirm CI for the domain separation branch, then migrate the existing crypto runtime behind compatibility imports before adding any US-stock data or broker integration.
