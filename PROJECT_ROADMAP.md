# AiPro Project Roadmap

Updated: 2026-07-19

## Project goal

Build a safe, maintainable multi-asset automated trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains remain isolated:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies
- `aipro/intelligence/` — broker-neutral news, sentiment, macro, filing, and feature inputs

Development order is offline tests, backtesting, paper trading, live-readiness review, and explicitly approved live trading. Each asset domain must pass this sequence independently. Capital, broker state, risk limits, order IDs, approval state, credentials, and daily performance baselines must never be shared implicitly.

## Portfolio baseline policy

1. Crypto and US-stock portfolios maintain independent daily baselines.
2. Crypto baseline = crypto cash + current crypto holdings market value.
3. US-stock baseline = US-stock cash + current US-stock holdings market value.
4. Combined totals are reporting-only and never replace either risk baseline.
5. The US-stock broker remains undecided until the intelligence and safety foundation is complete.

## Current status

Overall completion: **97%**

### Completed

- [x] Entry-point structure and crypto runtime ownership through `aipro/crypto/application.py`
- [x] PAPER default, double LIVE guard, persistent KST baseline, and HALTED latch
- [x] Persistent PAPER cash, positions, immutable order IDs, and restart recovery
- [x] Historical replay, strict CSV validation, dataset fingerprinting, and readiness reports
- [x] Independent crypto and disabled-by-default US-stock namespaces
- [x] Upbit public quotation adapter with freshness and provider-health gates
- [x] Isolated GET-only authenticated Upbit inspection and immutable snapshots
- [x] Fail-closed order lookup and duplicate-resubmission blocking
- [x] Immutable `MATCH`, `MISMATCH`, and `STALE` comparison evidence
- [x] Deterministic supervised PAPER validation and append-only evidence
- [x] Recent `MATCH` comparison evidence required for validation PASS
- [x] Restart-safe `/ai_upbit_go -> /confirm -> /go` approval state machine
- [x] Expiring approval state, invalid-order rejection, and Telegram status reporting
- [x] Provider-neutral normalized news article and sentiment contracts
- [x] Multi-provider news collection with provider-health isolation
- [x] URL/headline deduplication, symbol relevance, and confidence-weighted sentiment fusion
- [x] Finnhub company-news and Alpha Vantage sentiment adapters
- [x] Regression tests and GitHub Actions workflow

### In progress

- [ ] Confirm the news-intelligence feature branch in GitHub Actions
- [ ] Perform a supervised least-privilege read-only account probe with a real IP-restricted key
- [ ] Validate Upbit public market data during sustained supervised PAPER operation
- [ ] Complete compatibility cleanup for legacy root-level crypto imports

### Not started

#### Crypto

- [ ] Authenticated order submission, kept absent until every readiness and supervised-operation gate passes

#### US stocks

- [ ] Keep broker-neutral interfaces until the AI foundation is complete
- [ ] Select read-only market data and a supported broker later
- [ ] Momentum/gap scanner, liquidity filters, USD state, calendar, backtest, and readiness gate

#### Shared intelligence

- [ ] Append-only news cache and ingestion evidence
- [ ] Provider retry, rate-limit, freshness, and circuit-breaker policy
- [ ] Native provider sentiment mapping and event classification
- [ ] FRED macroeconomic regime inputs
- [ ] SEC EDGAR filing analysis
- [ ] Chart-pattern features
- [ ] EV and volatility-based sizing
- [ ] Model training and inference pipeline
- [ ] Deployment and operational monitoring

## Current behavior

1. Execution remains `run.py -> telegram.py -> main.py -> TradingApplication`.
2. PAPER remains the source of truth; authenticated inspection cannot alter strategy, balances, orders, or baselines.
3. Exchange snapshots, comparisons, validation results, and approval events are persistent evidence.
4. Supervised PAPER validation requires recent `MATCH` evidence.
5. LIVE approval must follow the exact expiring three-command sequence and survives restart.
6. Completing the approval sequence records intent only; it never enables LIVE mode or submits orders.
7. News providers are replaceable and return normalized deterministic article records.
8. News provider failures are visible in provider health and cannot fabricate strategy input.
9. News and sentiment remain disconnected from order submission until PAPER feature validation is implemented.
10. Order creation, cancellation, withdrawal, deposit management, and mutation endpoints remain absent or blocked.

## Current gaps and risks

1. Real least-privilege Upbit credentials have not been exercised in supervised operation.
2. Sustained PAPER operation has not yet proven timestamp tolerances and sparse-market behavior.
3. Runtime validation observations are still supplied explicitly rather than collected automatically.
4. Backtests use fixed slippage and do not model depth or partial fills.
5. Approval completion is not an authorization to trade; authenticated order submission remains intentionally absent.
6. News adapters do not yet have persistent cache, rate-limit evidence, retries, or circuit breakers.
7. Alpha Vantage native ticker sentiment values are not yet preserved in normalized observations.
8. Evidence export signing and retention/deletion policy are not implemented.
9. US-stock broker, market data, FX, tax, calendar, and fractional-share behavior remain undecided.

## Immediate priority

### P0 — Confirm CI

- Require the full news-intelligence regression suite to pass.
- Verify normalization, deterministic fingerprinting, deduplication, provider isolation, and sentiment fusion.

### P1 — Persistent news ingestion

- Add append-only cache and ingestion evidence with freshness and provider metadata.
- Add bounded retries, rate-limit handling, and provider circuit breakers.

### P2 — Macro and filing intelligence

- Add FRED macro-regime inputs and SEC EDGAR filing-event normalization.
- Keep all intelligence features broker-neutral and PAPER-only.

### P3 — Supervised crypto PAPER operation

- Record at least 24 completed cycles, restart recovery, HALTED behavior, provider health, source freshness, unique order IDs, runtime stability, and recent `MATCH` evidence.
- Persist immutable evidence to a protected local database.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded.

## Next action

Confirm feature-branch CI, then add append-only news ingestion evidence and provider resilience before connecting normalized intelligence features to PAPER strategy evaluation.
