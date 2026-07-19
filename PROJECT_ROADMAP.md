# AiPro Project Roadmap

Updated: 2026-07-19

## Project goal

Build a safe, maintainable multi-asset automated-trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains remain isolated:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies
- `aipro/intelligence/` — broker-neutral intelligence inputs

Crypto and US-stock capital, broker state, risk limits, approval state, credentials, order IDs, and daily baselines must never be combined implicitly.

## V1 foundation status

Overall completion: **100%**

### Completed

- [x] Preserve `run.py -> telegram.py -> main.py -> TradingApplication`
- [x] PAPER default, double LIVE guard, persistent KST baseline, and HALTED latch
- [x] Persistent PAPER cash, positions, average prices, immutable order IDs, and restart recovery
- [x] Historical replay, strict dataset validation, fingerprints, and readiness reports
- [x] Independent crypto and disabled-by-default US-stock namespaces
- [x] Upbit public quotation adapter with freshness and provider-health gates
- [x] Isolated GET-only authenticated Upbit inspection with immutable evidence
- [x] Fail-closed duplicate lookup and resubmission blocking
- [x] Immutable `MATCH`, `MISMATCH`, and `STALE` reconciliation evidence
- [x] Deterministic supervised PAPER validation requiring recent `MATCH` evidence
- [x] Restart-safe expiring `/ai_upbit_go -> /confirm -> /go` approval-intent flow
- [x] Provider-neutral normalized news and sentiment contracts
- [x] Finnhub news and Alpha Vantage sentiment adapters
- [x] URL/headline deduplication, symbol relevance, and sentiment fusion
- [x] Bounded retry, sliding-window rate limiting, circuit breaker, and TTL cache
- [x] Append-only intelligence execution evidence with mutation blocking
- [x] Alpha Vantage native ticker sentiment preservation
- [x] Deterministic event classification
- [x] Freshness-gated PAPER-only intelligence feature snapshots
- [x] Deterministic SHA-256 feature fingerprints
- [x] Regression tests and GitHub Actions workflow
- [x] Safety and limitation documentation

## V1 safety boundary

1. PAPER remains the source of truth.
2. Approval completion records operator intent only and never enables LIVE trading.
3. Authenticated order creation, cancellation, withdrawals, deposits, and account mutation remain absent.
4. Intelligence snapshots are data-only and cannot alter balances, positions, risk state, baselines, or approvals.
5. Missing or stale comparison and intelligence evidence fails closed.
6. No claim of profitability or production readiness is made by reaching 100% V1 completion.

## V1 known limitations

- Real least-privilege Upbit credentials have not completed supervised IP-restricted operation.
- Sustained PAPER operation has not yet collected the required operational evidence window.
- Backtests still use simplified slippage and do not model full order-book depth or all partial-fill cases.
- Evidence export signing and retention/deletion policy remain unimplemented.
- US-stock broker, FX, tax, calendar, and fractional-share behavior remain intentionally undecided.

## V2 operational and research backlog

These are future expansions, not unfinished V1 foundation work:

### Supervised operation

- Run and record at least 24 supervised PAPER cycles.
- Verify restart recovery, HALTED behavior, public-data freshness, provider health, unique order IDs, recent `MATCH` evidence, and runtime stability.
- Perform a least-privilege read-only Upbit probe using an IP-restricted key.

### Intelligence expansion

- FRED macroeconomic regime inputs
- SEC EDGAR filing-event normalization
- Chart-pattern features
- EV and volatility-based position sizing
- Model training, evaluation, drift detection, and inference pipeline

### US stocks

- Select a supported read-only data provider and broker later.
- Add USD-isolated state, trading calendar, scanner, liquidity rules, backtest, PAPER validation, and independent readiness gates.

### Deployment

- Protected evidence backups and signing
- Runtime monitoring and alerting
- Secret rotation and operational runbooks
- Controlled deployment after PAPER evidence review

## Completion policy

A V1 task is complete only when implementation, tests, documentation, limitations, and safety boundaries are recorded. V2 items may not be treated as permission to add authenticated order submission.

## Next action

Execute the V2 supervised PAPER evidence run. Keep authenticated order submission absent until operational evidence and a separate live-readiness review pass.
