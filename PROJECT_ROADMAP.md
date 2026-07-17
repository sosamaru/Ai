# AiPro Project Roadmap

Last updated: 2026-07-17

## Project principles

- Preserve the execution chain: `run.py -> telegram.py -> main.py -> TradingApplication`.
- PAPER mode is the default and LIVE mode stays disabled until every release gate is satisfied.
- Prioritize maintainability, scalability, stability, auditability, and capital protection.
- Documentation and code must be synchronized in the same pull request.

## Current status

Estimated overall completion: **28%**

### Completed

- [x] Stable application entry chain
- [x] Environment-based settings
- [x] Console and file logging
- [x] Deterministic demo market data
- [x] Baseline momentum strategy
- [x] Position sizing and daily-loss HALT latch
- [x] Paper broker
- [x] SQLite event storage
- [x] Initial unit tests
- [x] Safe PAPER default

### Incomplete or insufficient

- [ ] Real Upbit authenticated REST/WebSocket adapter
- [ ] Exchange reconciliation for balances, orders, and fills
- [ ] Idempotent order submission and duplicate-order protection
- [ ] Retry, timeout, circuit-breaker, and rate-limit policies
- [ ] Persistent portfolio and session baseline recovery after restart
- [ ] Telegram authentication, command authorization, and confirmation workflow
- [ ] Backtesting engine with fees, slippage, latency, and walk-forward validation
- [ ] Long-running paper-trading soak test and daily report
- [ ] Strategy registry, feature pipeline, regime model, and model versioning
- [ ] Secret management and key rotation procedure
- [ ] Health checks, metrics, alerting, backup, and disaster recovery
- [ ] Deployment manifests for VPS/container operation
- [ ] LIVE release checklist and rollback procedure

## Delivery stages

### Stage 0 — Foundation and governance

Status: **IN PROGRESS**

Exit criteria:

- [x] Roadmap exists and reflects actual repository state
- [x] Automated test workflow exists
- [x] Formatting, linting, and type-checking configuration exists
- [x] Safe environment template exists
- [ ] Test suite passes in GitHub Actions
- [ ] Architecture and security documents are reviewed

### Stage 1 — Reliable paper-trading core

Target completion: 45%

- [ ] Define broker, market-data, strategy, risk, and storage protocols
- [ ] Add persistent portfolio state and restart recovery
- [ ] Add deterministic clock abstraction
- [ ] Add order lifecycle state machine
- [ ] Add idempotency keys and order deduplication
- [ ] Add structured domain events
- [ ] Add fee/slippage-aware PnL accounting
- [ ] Add daily KST baseline reset tests
- [ ] Add HALTED state persistence and `/go`-only recovery tests

Release gate: no uncaught exception during a 7-day simulated soak test.

### Stage 2 — Backtesting and validation

Target completion: 60%

- [ ] Historical candle loader and local cache
- [ ] Event-driven replay engine
- [ ] Fees, spread, slippage, partial fills, and latency simulation
- [ ] Train/validation/test split without look-ahead leakage
- [ ] Walk-forward analysis
- [ ] Benchmark comparison and ablation reports
- [ ] Risk metrics: drawdown, volatility, Sharpe, Sortino, turnover, exposure
- [ ] Reproducible report artifact with configuration hash

Release gate: strategy must beat the configured benchmark after costs without violating drawdown limits across multiple market regimes.

### Stage 3 — Exchange integration in read-only mode

Target completion: 72%

- [ ] Upbit public market-data adapter
- [ ] Authenticated balance and order-history client
- [ ] Request signing, nonce handling, timeout, retry, and rate limiting
- [ ] Clock-drift checks
- [ ] Balance/order/fill reconciliation
- [ ] Read-only production observation for at least 7 days

Release gate: local state and exchange state remain reconciled with zero unexplained drift.

### Stage 4 — Telegram operations and paper deployment

Target completion: 82%

- [ ] Authorized chat-ID allowlist
- [ ] `/status`, `/positions`, `/risk`, `/halt`, `/confirm`, `/go`
- [ ] Two-step confirmation for dangerous actions
- [ ] Command audit log
- [ ] Health heartbeat and exception alerts
- [ ] Docker/VPS deployment with automatic restart
- [ ] Encrypted backups and restore test

Release gate: 30-day PAPER deployment without unresolved critical incidents.

### Stage 5 — Guarded LIVE pilot

Target completion: 92%

- [ ] `AIPRO_LIVE_CONFIRM=YES`
- [ ] `ENABLE_LIVE_TRADING=1`
- [ ] Positive `MAX_ORDER_KRW` with a conservative cap
- [ ] Kill switch and account-wide loss limit
- [ ] Small-capital canary orders only
- [ ] Manual review of every session
- [ ] Tested rollback to PAPER mode

Release gate: explicit owner approval after all prior gates pass. Profit is not guaranteed and LIVE trading remains optional.

### Stage 6 — Advanced AI and strategy portfolio

Target completion: 100%

- [ ] Feature registry with fixed schemas and versioning
- [ ] Regime detection
- [ ] News/sentiment adapter with source quality controls
- [ ] Model registry, drift monitoring, and rollback
- [ ] Ensemble and expected-value selection
- [ ] Volatility-aware sizing and portfolio constraints
- [ ] Shadow deployment before model promotion

## Current risks

1. **Financial risk:** the current repository must not place real orders.
2. **State risk:** restart recovery and exchange reconciliation are not complete.
3. **Validation risk:** a baseline strategy is not evidence of durable profitability.
4. **Security risk:** production secret handling and Telegram authorization are incomplete.
5. **Operational risk:** monitoring, backup, and deployment recovery are incomplete.

## Next three priorities

1. Formalize interfaces and implement persistent restart-safe paper portfolio/order state.
2. Build the cost-aware replay/backtesting engine and validation report.
3. Implement read-only Upbit integration with reconciliation before any order endpoint.

## Definition of done for every feature

- Code follows the existing application flow and has clear boundaries.
- Unit and integration tests cover success, failure, restart, and edge cases.
- Security and failure behavior are documented.
- `PROJECT_ROADMAP.md` is updated with completion, gaps, remaining work, and next priority.
- No LIVE capability is enabled merely because code compiles or a small test passes.
