# AiPro Project Roadmap

Updated: 2026-07-18

## Project goal

Build a safe, maintainable multi-asset automated trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains remain isolated:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies

Development order:

1. Offline tests
2. Backtesting
3. Paper trading
4. Live-readiness review
5. Explicitly approved live trading

Each asset domain must pass this sequence independently. Capital, broker state, risk limits, order IDs, approval state, credentials, and daily performance baselines must never be shared implicitly between crypto and US stocks.

## Portfolio baseline policy

1. Crypto and US-stock portfolios maintain independent daily baselines.
2. Crypto daily baseline = crypto cash + current market value of crypto holdings.
3. US-stock daily baseline = US-stock cash + current market value of US-stock holdings.
4. Each baseline resets once per day from that domain's current account value and is used only for that domain's daily return and risk calculations.
5. A combined total may be displayed for reporting but never replaces either independent baseline.
6. The US-stock policy reserves approximately KRW 200,000 for its domain, with a separate high-volatility momentum allocation.

## Current status

Overall completion: **82%**

### Completed

- [x] Entry-point structure and crypto runtime ownership through `aipro/crypto/application.py`
- [x] PAPER default and double LIVE guard
- [x] Persistent KST trading date, independent crypto/US-stock baselines, and HALTED latch
- [x] Persistent PAPER cash, positions, average prices, immutable order IDs, and interrupted-cycle recovery
- [x] Read-only reconciliation and bounded broker retry policy
- [x] Deterministic historical replay with fees, slippage, sizing, drawdown, win rate, exposure, and reports
- [x] Strict CSV historical-data loader with schema validation and SHA-256 fingerprinting
- [x] Independent PAPER-readiness PASS/FAIL reports with sample, trade, return, drawdown, exposure, regime, and out-of-sample checks
- [x] Immutable completed-order archive with active retention, duplicate-ID protection, restart recovery, and full reconciliation
- [x] Disabled-by-default US-stock domain and separate namespace/capital policy
- [x] Upbit unauthenticated read-only quotation adapter
- [x] Batched ticker retrieval plus validated 60-minute candle momentum and volatility features
- [x] Bounded public-market-data timeout and retry handling
- [x] Opt-in `UPBIT` provider with deterministic `DEMO` remaining the default
- [x] Market-data latency, failure-count, last-success age, and status reporting gate
- [x] Fail-closed strategy/PAPER execution on unhealthy market data
- [x] Failed market-data cycle abort and immutable audit event
- [x] Upbit ticker/candle source timestamp parsing and preservation
- [x] Fail-closed rejection of missing, naive, stale, future, and inconsistent exchange timestamps
- [x] Exchange source timestamp and source-age health reporting
- [x] GitHub Actions regression tests for all completed components

### In progress

- [ ] Complete remaining compatibility cleanup for legacy root-level crypto imports
- [ ] Validate Upbit public market data during sustained supervised PAPER operation

### Not started

#### Crypto

- [ ] Authenticated Upbit account client with read-only balance/order inspection first
- [ ] Exchange order-ID reconciliation after timeout
- [ ] `/ai_upbit_go -> /confirm -> /go` live approval flow
- [ ] Authenticated order submission, disabled until readiness and supervised PAPER gates pass

#### US stocks

- [ ] Select and implement a read-only US-stock market-data adapter
- [ ] Select a supported broker and build PAPER adapter
- [ ] US momentum/gap scanner and liquidity filters
- [ ] Separate USD cash, positions, orders, database namespace, approval flow, and runtime risk controls
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

1. The execution path remains `run.py -> telegram.py -> main.py -> TradingApplication`.
2. Crypto and US-stock baselines and state namespaces remain independent.
3. The active broker remains PAPER only unless the existing explicit LIVE guards are satisfied.
4. `AIPRO_MARKET_DATA_PROVIDER=DEMO` is the safe default and performs no network calls.
5. `AIPRO_MARKET_DATA_PROVIDER=UPBIT` changes only the crypto price source and uses public quotation endpoints without credentials.
6. Upbit current prices are retrieved in one ticker request; recent 60-minute candles are retrieved per configured symbol.
7. Missing, malformed, duplicate, non-positive, non-finite, mismatched, or incorrectly ordered public data fails closed.
8. Upbit ticker and candle timestamps are normalized to timezone-aware UTC values and carried in each snapshot.
9. Missing, stale, future, naive, or inconsistent exchange timestamps block strategy decisions and PAPER orders.
10. Market-data retry attempts, timeout, latency, source age, and consecutive failures are bounded and reported.
11. An unhealthy provider blocks strategy decisions and PAPER orders and records a failed-cycle audit event.
12. Selecting Upbit market data does not enable account access or order submission.
13. Archived completed PAPER orders remain immutable and continue to participate in duplicate-ID checks and reconciliation.

## Current gaps and risks

1. Upbit candle intervals with no trades may be absent; sparse markets can fail validation.
2. Hourly return volatility is a basic feature and is not evidence of predictive value.
3. Backtests still use fixed slippage and do not model order-book depth or partial fills.
4. Open positions are marked to the latest supplied price at backtest end rather than forcibly liquidated.
5. Real account authentication and exchange order reconciliation remain unimplemented.
6. Exchange timestamps are validated against a single configured age threshold; sustained PAPER operation is still needed to tune tolerance safely.
7. Archived evidence has no signed export and deletion policy; automatic deletion remains disabled.
8. US-stock broker, data, calendar, FX, tax, and fractional-share behavior remain unimplemented.
9. Legacy baseline keys remain for rollback compatibility and need a retirement version before removal.

## Immediate priority

### P0 — Authenticated Upbit read-only account boundary

- Add credential loading without logging secrets.
- Implement account and order lookup only; no order creation.
- Keep private endpoints isolated from the public market adapter.
- Add timeout, authentication, permission-failure, and response-validation tests.

### P1 — Supervised crypto PAPER validation

- Run validated historical datasets through the readiness gate.
- Record dataset fingerprint, strategy/config version, and PAPER observation period.
- Require stable restart, reconciliation, HALTED, provider-health, and source-timestamp behavior.

### P2 — Exchange order reconciliation design

- Define timeout lookup and immutable exchange-order identity rules.
- Prevent duplicate submission after ambiguous network outcomes.
- Keep submission disabled until authenticated read-only inspection is proven.

### P3 — US-stock public data research

- Select a compliant data interface before code implementation.
- Document market calendar, delayed/real-time status, rate limits, and licensing constraints.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded.

## Next action

Merge exchange timestamp validation after final CI, then implement an isolated authenticated Upbit read-only account client with no order-creation capability.
