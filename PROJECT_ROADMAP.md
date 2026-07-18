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

Overall completion: **54%**

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
- [x] Successful GitHub Actions validation for deterministic order IDs
- [x] Read-only cash and position-quantity reconciliation
- [x] Reconciliation mismatch reporting without automatic state mutation
- [x] Successful GitHub Actions validation for read-only reconciliation
- [x] Bounded retry policy for transient broker failures
- [x] Permanent broker errors fail immediately without retry
- [x] Broker operation deadline and timeout error foundation
- [x] Extended order states: pending, partial, rejected, cancelled, and timeout

### In progress

- [ ] Confirm GitHub Actions for broker reliability policy
- [ ] Integrate reliability executor at exchange-adapter boundary
- [ ] Completed-order retention and archival policy
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

1. KST date, daily baseline, HALTED state, account state, orders, and active cycle survive restarts.
2. Duplicate client order IDs cannot apply the same paper fill twice.
3. Reconciliation reconstructs expected cash and quantities and never silently edits state.
4. Transient broker failures can be retried only up to a configured attempt limit.
5. Permanent broker failures are never retried.
6. Retry backoff is bounded and constrained by the overall operation deadline.
7. A result that returns after the deadline raises a timeout requiring reconciliation before another order attempt.
8. Real exchange authentication and order submission remain unimplemented and disabled.

## Current gaps and risks

1. The reliability executor is intentionally not wired into `PaperBroker`; local paper operations are synchronous and deterministic.
2. A real exchange adapter must reconcile an order ID after timeout before submitting it again.
3. Python cannot forcibly cancel an arbitrary blocking network call safely; the future HTTP adapter must also configure socket/connect/read timeouts.
4. Partial-fill fields and cancellation transitions are not yet represented in `OrderRecord` beyond status values.
5. Completed order history needs retention limits before long-running operation.
6. Reconciliation does not compare against an external exchange account because no authenticated Upbit client exists.
7. The application still uses demo market data and a paper broker only.

## Immediate priority

### P0 — Validate broker reliability

- Confirm GitHub Actions passes retry, timeout, and permanent-error tests.
- Verify existing persistence, reconciliation, liquidation, and Telegram tests remain green.

### P1 — Backtesting foundation

- Build deterministic historical replay without changing live-facing architecture.
- Record fees, slippage, drawdown, win rate, exposure, and trade chronology.
- Produce a machine-readable and human-readable performance report.

### P2 — Exchange-readiness

- Add read-only Upbit market data first.
- Apply HTTP connect/read timeouts at the adapter boundary.
- Require order lookup and reconciliation after ambiguous timeout outcomes.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, and next priority are all recorded.

## Next action

Confirm CI for the broker reliability branch, then begin the deterministic backtesting engine before any authenticated exchange integration.
