# AiPro Project Roadmap

Updated: 2026-07-19

## Project goal

Build a safe, maintainable multi-asset automated trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains remain isolated:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies

Development order is offline tests, backtesting, paper trading, live-readiness review, and explicitly approved live trading. Each asset domain must pass this sequence independently. Capital, broker state, risk limits, order IDs, approval state, credentials, and daily performance baselines must never be shared implicitly.

## Portfolio baseline policy

1. Crypto and US-stock portfolios maintain independent daily baselines.
2. Crypto baseline = crypto cash + current crypto holdings market value.
3. US-stock baseline = US-stock cash + current US-stock holdings market value.
4. Combined totals are reporting-only and never replace either risk baseline.
5. The US-stock broker remains undecided until the intelligence and safety foundation is complete.

## Current status

Overall completion: **94%**

### Completed

- [x] Entry-point structure and crypto runtime ownership through `aipro/crypto/application.py`
- [x] PAPER default, double LIVE guard, persistent KST baseline, and HALTED latch
- [x] Persistent PAPER cash, positions, average prices, immutable order IDs, and restart recovery
- [x] Historical replay, strict CSV validation, dataset fingerprinting, and readiness reports
- [x] Independent crypto and disabled-by-default US-stock namespaces
- [x] Upbit public quotation adapter with source freshness and provider-health gates
- [x] Isolated GET-only authenticated Upbit inspection with secret-safe configuration
- [x] Immutable read-only account snapshots and database mutation blocking
- [x] Fail-closed order lookup and duplicate-resubmission blocking
- [x] Immutable `MATCH`, `MISMATCH`, and `STALE` comparison evidence
- [x] Deterministic supervised PAPER validation and append-only evidence
- [x] Recent comparison evidence required for validation PASS
- [x] Missing, `MISMATCH`, `STALE`, and expired `MATCH` evidence fail closed
- [x] Comparison metadata and fingerprint are included without mutating PAPER state
- [x] Regression tests for persistence, reconciliation, validation, and namespace isolation
- [x] GitHub Actions regression workflow

### In progress

- [ ] Confirm the comparison-validation feature branch in GitHub Actions
- [ ] Perform a supervised least-privilege read-only account probe with a real IP-restricted key
- [ ] Validate Upbit public market data during sustained supervised PAPER operation
- [ ] Complete compatibility cleanup for legacy root-level crypto imports

### Not started

#### Crypto

- [ ] `/ai_upbit_go -> /confirm -> /go` expiring and restart-safe approval flow
- [ ] Authenticated order submission, kept absent until all readiness gates pass

#### US stocks

- [ ] Keep broker-neutral interfaces until the AI foundation is complete
- [ ] Select read-only market data and a supported broker later
- [ ] Momentum/gap scanner, liquidity filters, USD state, calendar, backtest, and readiness gate

#### Shared intelligence

- [ ] Provider-based news ingestion: Finnhub primary, Alpha Vantage sentiment support
- [ ] FRED macroeconomic regime inputs
- [ ] SEC EDGAR filing analysis
- [ ] Chart-pattern features
- [ ] EV and volatility-based sizing
- [ ] Model training and inference pipeline
- [ ] Deployment and operational monitoring

## Current behavior

1. Execution remains `run.py -> telegram.py -> main.py -> TradingApplication`.
2. PAPER is the source of truth and authenticated inspection cannot alter strategy, balances, orders, or baselines.
3. Exchange snapshots and comparison results are append-only evidence.
4. Supervised PAPER validation now requires comparison evidence that is present, exactly `MATCH`, and no older than the configured maximum age, 300 seconds by default.
5. A validation `PASS` is readiness evidence only and never authorizes LIVE trading.
6. Order creation, cancellation, withdrawal, deposit management, and mutation endpoints remain absent or blocked.

## Current gaps and risks

1. Real least-privilege Upbit credentials have not been exercised in supervised operation.
2. Local evidence databases contain sensitive financial and operational values and require restrictive permissions and protected backups.
3. Runtime observations are still supplied explicitly rather than collected automatically.
4. Sustained PAPER operation has not yet proven exchange timestamp tolerances and sparse-market behavior.
5. Backtests use fixed slippage and do not yet model depth or partial fills.
6. Evidence export signing and retention/deletion policy are not implemented.
7. US-stock broker, market data, FX, tax, calendar, and fractional-share behavior remain intentionally undecided.

## Immediate priority

### P0 — Confirm CI

- Require all branch tests to pass.
- Verify deterministic fingerprints and fail-closed comparison cases.

### P1 — Live approval state machine

- Implement `/ai_upbit_go -> /confirm -> /go` as an expiring, restart-safe sequence.
- Keep order submission absent.

### P2 — Supervised crypto PAPER operation

- Record at least 24 completed cycles, restart recovery, HALTED behavior, provider health, source freshness, unique order IDs, runtime stability, and recent `MATCH` evidence.
- Persist immutable evidence to a protected local database.

### P3 — Shared intelligence foundation

- Add replaceable news-provider contracts and normalized article models.
- Add sentiment, macro-regime, filing-event, chart-pattern, and EV sizing layers without coupling them directly to order submission.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded.

## Next action

Confirm feature-branch CI, then implement the expiring restart-safe live approval state machine while keeping authenticated order submission absent.