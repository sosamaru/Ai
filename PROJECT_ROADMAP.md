# AiPro Project Roadmap

Last updated: 2026-07-17

## Architecture contract

The execution path must remain:

`run.py -> telegram.py -> main.py -> TradingApplication`

New components must be injected behind `TradingApplication` rather than bypassing this path.

## Current status

Overall completion: **22%**

The repository is a safe offline PAPER MVP. It can generate deterministic demo market data, make baseline momentum decisions, size positions, execute simulated orders, record SQLite events, and halt on a daily loss threshold.

### Completed

- [x] Stable entry flow
- [x] Environment-based configuration
- [x] PAPER mode default
- [x] Double LIVE guard
- [x] Deterministic demo market-data adapter
- [x] Baseline momentum strategy
- [x] Position sizing
- [x] Daily-loss HALT behavior
- [x] Paper broker
- [x] SQLite event storage
- [x] Console/file logging
- [x] Initial unit-test framework
- [x] CI workflow
- [x] Configuration template and validation tests

### Incomplete and reasons

- [ ] Real Upbit market-data adapter: authenticated/public API client not implemented
- [ ] Real Upbit order adapter: order submission is intentionally blocked
- [ ] Exchange reconciliation: no authoritative comparison of local and exchange balances/orders
- [ ] Idempotency: no durable client order key or duplicate-order prevention
- [ ] Retry policy: no bounded exponential backoff or error classification
- [ ] Partial-fill handling: no fill threshold, timeout, cancel, or replacement order flow
- [ ] Persistent daily baseline: baseline resets when the process restarts
- [ ] Persistent HALTED latch: halt state is not durable across restarts
- [ ] KST midnight rollover: daily accounting reset is not implemented
- [ ] Telegram command control: entry layer exists but no bot command handlers
- [ ] Backtesting engine: no historical candle replay or transaction-cost model
- [ ] Paper-trading validation: no multi-week acceptance report
- [ ] Strategy ensemble: news, sentiment, chart patterns, regime, guardian, EV, and volatility sizing are not implemented
- [ ] Model lifecycle: no dataset versioning, feature schema enforcement, training, evaluation, registry, or rollback
- [ ] Operations: no health checks, metrics, alerts, deployment manifest, backup, or recovery runbook
- [ ] Security: no external secret manager, credential rotation, or least-privilege deployment

## Delivery phases

### Phase 1 — Foundation and safety

Target completion: 35%

- Configuration hardening and `.env.example`
- CI tests on supported Python versions
- Persistent session state and KST daily baseline
- Persistent HALTED latch and explicit `/go` recovery contract
- Broker and market-data interfaces
- Structured error taxonomy and bounded retry utility
- Order intent/idempotency model

Exit criteria: process restarts cannot silently reset loss controls, and all exchange-facing actions are abstracted and testable.

### Phase 2 — Backtest and paper trading

Target completion: 55%

- Historical candle repository
- Replay engine
- Fees, spread, slippage, and partial-fill simulation
- Walk-forward evaluation
- Risk and performance report
- Paper-trading acceptance suite

Exit criteria: reproducible backtests and at least 14 consecutive days of paper trading with no critical reconciliation errors.

### Phase 3 — Upbit read-only integration

Target completion: 68%

- Public market data
- Authenticated balances and open-order reads
- Clock drift and nonce handling
- Rate limiting and bounded retries
- Read-only reconciliation dashboard

Exit criteria: local state matches exchange state without submitting orders.

### Phase 4 — Controlled live rehearsal

Target completion: 80%

- Order adapter behind existing LIVE guards
- Maximum order KRW guard
- Idempotent order submission
- Cancel/replace and partial-fill handling
- Emergency liquidation workflow
- Telegram approval sequence: `/ai_upbit_go -> /confirm -> /go`

Exit criteria: live rehearsal uses minimum order sizes, predefined loss caps, and a documented rollback procedure.

### Phase 5 — Strategy and ML expansion

Target completion: 92%

- Feature schema fixed and versioned
- Regime classifier
- Chart-pattern and momentum ensemble
- News/sentiment adapter with stale-data controls
- Expected-value and volatility-aware sizing
- Model registry, shadow evaluation, and rollback

Exit criteria: every model is compared against the baseline after costs and cannot bypass risk controls.

### Phase 6 — Production operations

Target completion: 100%

- VPS/container deployment
- Health checks and watchdog
- Metrics and alerting
- Database backup and restoration test
- Secret manager and credential rotation
- Incident response and recovery runbook
- Release checklist and change log

Exit criteria: unattended operation is observable, recoverable, and fails safe.

## Immediate priorities

1. Persist KST daily baseline and HALTED state.
2. Introduce exchange-neutral interfaces, retry policy, and order idempotency.
3. Build the historical replay/backtesting engine before any real-order implementation.

## Safety decision

LIVE trading remains blocked. No real order adapter should be merged until Phase 2 and Phase 3 exit criteria are met.