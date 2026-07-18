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

Overall completion: **50%**

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
- [x] Persistent paper cash, positions, and average prices
- [x] Safe recovery from invalid persisted paper-account state
- [x] Immutable paper buy/sell event records in SQLite
- [x] Paper-account restart, liquidation, corruption, and invalid-trade tests
- [x] Successful GitHub Actions validation for paper-account persistence
- [x] Application-level forced-liquidation restart coverage
- [x] Successful GitHub Actions validation for forced-liquidation coverage
- [x] Immutable paper order records with explicit side and status
- [x] Persistent client order identifiers across restarts
- [x] Duplicate paper buy and sell requests applied at most once
- [x] Idempotent no-position sell results
- [x] Successful GitHub Actions validation for idempotent paper orders
- [x] Deterministic application order IDs from date, cycle, side, and symbol
- [x] Persistent active-cycle recovery after interrupted execution
- [x] Application status exposes cycle sequence and active cycle
- [x] Successful GitHub Actions validation for deterministic application order IDs
- [x] Read-only cash and position-quantity reconciliation
- [x] Reconciliation mismatch reporting without automatic state mutation
- [x] Reconciliation summary exposed through application status

### In progress

- [ ] Confirm GitHub Actions for read-only reconciliation
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
4. Paper cash, positions, average prices, and completed order records survive restarts.
5. Invalid or corrupted paper-account state is rejected and safely reinitialized.
6. Forced liquidation persists empty positions and reduced cash before restart.
7. A restarted HALTED application cannot silently create new positions.
8. Repeated `submit_buy()` or `submit_sell_all()` calls with the same client order ID return the original immutable result without changing balances twice.
9. Orders expose explicit `BUY`/`SELL` sides and `FILLED`/`NO_POSITION` states.
10. Each application cycle receives a persistent sequence and deterministic order IDs.
11. Interrupted cycles remain active so a restarted process reuses the same order IDs.
12. A cycle is cleared only after the full application run completes successfully.
13. Reconciliation rebuilds expected cash and net position quantities from filled immutable orders.
14. Reconciliation only reports mismatches and never silently edits cash, positions, or orders.
15. Application status exposes reconciliation health and issue count.
16. Existing `buy()` and `sell_all()` compatibility methods remain available.
17. Telegram is disabled when no token is configured; console mode runs one cycle.
18. Unauthorized chat IDs cannot inspect or change application state.
19. Real exchange orders remain unimplemented and disabled.

## Current gaps and risks

1. Reconciliation does not yet compare against an external exchange account because no Upbit account client exists.
2. Average-price reconstruction is intentionally excluded because legacy random order IDs do not guarantee chronological replay.
3. Completed order history is stored with the paper-account snapshot and needs retention limits before long-running operation.
4. Broker operations do not implement bounded retries, timeout handling, partial fills, or cancellation states.
5. A permanently failing cycle requires an explicit administrative recovery policy before production operation.
6. Telegram bot tokens remain environment-managed; a production secret manager is not integrated.
7. The application still uses demo market data and a paper broker only.
8. The three-step live approval flow is intentionally not implemented yet.

## Immediate priority

### P0 — Validate reconciliation

- Confirm GitHub Actions passes for consistent-account and mismatch-detection tests.
- Verify reconciliation performs no state mutation.
- Verify all previous order, liquidation, persistent-state, and Telegram tests remain green.

### P1 — Broker reliability

- Add bounded retry and timeout policies.
- Define pending, rejected, cancelled, and partially filled states.
- Add completed-order retention or archival policy.

### P2 — Validation foundation

- Build deterministic replay/backtesting support.
- Record fees, slippage, drawdown, win rate, and exposure.
- Define measurable paper-trading acceptance criteria.

### P3 — Exchange integration

- Implement read-only Upbit market data first.
- Add authenticated account reconciliation after safe credential handling is designed.
- Keep order submission disabled until readiness criteria pass.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, and next priority are all recorded.

## Next action

Confirm CI for read-only reconciliation, then implement bounded retry and timeout behavior without enabling real exchange trading.
