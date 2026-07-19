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

## V2 status

Current milestone: **authorization and PAPER-training foundation**

### Completed in current milestone

- [x] Email OTP first-factor state machine
- [x] Separate second-factor verification contract
- [x] Salted OTP digest, expiry, failed-attempt lockout, and immediate revocation
- [x] Temporary LIVE authorization lease with forced reauthentication after expiry
- [x] Global stop/revocation path
- [x] Alpaca PAPER minimum 30-day readiness policy
- [x] Session, order-count, expectancy, drawdown, daily-loss, stale-data, duplicate-order, and reconciliation gates
- [x] Deterministic PAPER evidence fingerprint
- [x] Regression tests and design documentation

### Next implementation milestones

- [ ] SMTP or transactional-email OTP sender adapter with secret-safe configuration
- [ ] TOTP verifier and enrollment/recovery procedure
- [ ] Persist authorization state and append-only authorization audit evidence
- [ ] Connect Telegram commands without allowing command-only bypass
- [ ] Alpaca PAPER account, market-data, order, fill, and reconciliation adapters
- [ ] Automatic 30-day PAPER evidence collector and daily report
- [ ] Upbit authenticated test-order/preflight adapter before any real order endpoint
- [ ] Upbit supervised live-data collector with order submission disabled
- [ ] Expert-claim extraction, source reliability scoring, and outcome tracking
- [ ] Chart, volatility, liquidity, macro, filing, and event feature expansion
- [ ] Risk-adjusted EV ensemble, drift detection, and strategy-ablation evaluation
- [ ] Independent live-readiness review before creating a minimal real-order adapter

## Mandatory future real-order gates

A future order adapter must require every gate below simultaneously:

1. Explicit LIVE environment guards.
2. Active two-factor authorization lease.
3. Recent PAPER validation PASS.
4. At least 30 days of qualifying Alpaca PAPER evidence for the US-stock domain.
5. Recent reconciliation `MATCH` evidence.
6. Fresh market and intelligence data.
7. Healthy required providers.
8. Daily-loss, drawdown, exposure, liquidity, and position-size limits.
9. Unique client order identifier and duplicate-order rejection.
10. Order preflight/test validation when supported.
11. Global kill switch not active.

An OTP, expert opinion, high confidence score, or recent profit may never bypass a failed safety gate.

## V2 investment-intelligence policy

- Expert opinions are timestamped evidence, not direct commands.
- Each claim must be mapped to symbols, events, horizon, and measurable outcomes.
- Source weights must be learned from out-of-sample historical accuracy and must decay when performance deteriorates.
- News, filings, macro, chart, volume, volatility, liquidity, regime, and portfolio risk must be combined.
- The optimization target is risk-adjusted expected value and controlled drawdown, not maximum aggression.
- Disagreement, stale data, regime uncertainty, and model drift reduce or block position size.
- No profitability guarantee is permitted.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, and safety boundaries are recorded. Real-order code remains prohibited until the independent live-readiness review passes.

## Next action

Implement the concrete email OTP sender, TOTP verifier, persisted authorization audit store, and Alpaca PAPER adapter while keeping real order submission absent.