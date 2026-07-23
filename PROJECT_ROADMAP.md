# AiPro Project Roadmap

Updated: 2026-07-23

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

## V2 integration status

Development completion: **100% for the approved non-live integration scope**

### Completed

- [x] Email OTP first-factor state machine
- [x] SMTP OTP sender with environment-only secret configuration
- [x] RFC 6238 TOTP second-factor verifier
- [x] Salted OTP digest, expiry, failed-attempt lockout, and immediate revocation
- [x] Temporary LIVE authorization lease with forced reauthentication after expiry
- [x] Global stop/revocation path
- [x] Atomic authorization-state persistence across restart
- [x] Append-only authorization audit evidence with UPDATE/DELETE blocking
- [x] Alpaca PAPER-only account, order, order-list, and reconciliation lookup adapter
- [x] Alpaca live-domain rejection and separate PAPER credential names
- [x] Alpaca PAPER minimum 30-day readiness policy
- [x] Session, order-count, expectancy, drawdown, daily-loss, stale-data, duplicate-order, and reconciliation gates
- [x] Upbit authenticated `/v1/orders/test` preflight adapter
- [x] Hard separation from the real Upbit `/v1/orders` endpoint
- [x] Deterministic regression tests for authorization, restart recovery, PAPER-domain enforcement, and test-order safety
- [x] Secret-safe deployment and operation documentation

## V3 intelligence expansion status

Current milestone completion: **50%**

### Completed

- [x] Broker-neutral FRED observation contract and client
- [x] CPI, effective federal funds rate, and unemployment normalization
- [x] Missing/stale macro-data fail-closed eligibility gate
- [x] Deterministic PAPER-only macro regime snapshot and SHA-256 fingerprint
- [x] SEC EDGAR read-only submissions client with identifying User-Agent enforcement
- [x] Filing-event normalization for reports, material events, ownership, offerings, insider transactions, and proxies
- [x] Missing/stale filing fail-closed eligibility gate and deterministic fingerprints
- [x] Validated OHLCV market-bar contract with duplicate and malformed-bar rejection
- [x] Deterministic return, volatility, ATR, volume, spread, liquidity, and trend features
- [x] Missing, insufficient, stale, future, and excessive-zero-volume fail-closed gates
- [x] Offline regression tests and safety documentation

### Remaining

- [ ] Filing text/XBRL fact extraction, materiality scoring, and historical outcome evaluation
- [ ] Versioned combined PAPER feature vector
- [ ] Walk-forward model training and out-of-sample evaluation
- [ ] Drift detection, feature ablation, and model registry
- [ ] Risk-adjusted EV and volatility-based position sizing
- [ ] Independent crypto and US-stock PAPER strategy validation

## Development boundary

The software development package is complete for V1 and V2, but this does **not** mean real-money trading is approved.

1. Real Upbit order creation remains absent.
2. Alpaca integration accepts only `https://paper-api.alpaca.markets`.
3. Upbit integration calls only `POST /v1/orders/test`, which validates but does not create an order.
4. Email OTP and TOTP grant only a temporary authorization lease; they do not bypass risk or readiness gates.
5. Authorization secrets, SMTP passwords, broker keys, TOTP secrets, and OTP plaintext must never be committed.
6. An OTP, expert opinion, confidence score, filing event, macro regime, market feature, or recent profit may never bypass a failed safety gate.

## Operational validation still required

These are real-world evidence runs, not unfinished coding tasks:

- [ ] Configure a dedicated SMTP or transactional-email account and confirm delivery to the owner email.
- [ ] Enroll the TOTP secret in an authenticator application and store recovery material offline.
- [ ] Add actual Alpaca PAPER credentials and run at least 30 calendar days.
- [ ] Collect sufficient sessions and orders while satisfying expectancy, drawdown, daily-loss, freshness, duplicate-order, and reconciliation gates.
- [ ] Add an IP-restricted Upbit key and execute supervised test-order/preflight checks only.
- [ ] Run the Upbit live-data collector with order creation disabled.
- [ ] Review evidence and produce a separate live-readiness decision.

## Mandatory future real-order gates

A future minimal real-order adapter may be considered only after every gate below passes simultaneously:

1. Explicit LIVE environment guards.
2. Active email OTP plus TOTP authorization lease.
3. Recent PAPER validation PASS.
4. At least 30 days of qualifying PAPER evidence for the relevant asset domain.
5. Recent reconciliation `MATCH` evidence.
6. Fresh market and intelligence data.
7. Healthy required providers.
8. Daily-loss, drawdown, exposure, liquidity, and position-size limits.
9. Unique client order identifier and duplicate-order rejection.
10. Successful order preflight/test validation when supported.
11. Global kill switch not active.
12. Independent live-readiness review approval.

## Investment-intelligence policy

- Expert opinions are timestamped evidence, not direct commands.
- Each claim must be mapped to symbols, events, horizon, and measurable outcomes.
- Source weights must be learned from out-of-sample historical accuracy and decay when performance deteriorates.
- News, filings, macro, chart, volume, volatility, liquidity, regime, and portfolio risk must be combined.
- The optimization target is risk-adjusted expected value and controlled drawdown, not maximum aggression.
- Disagreement, stale data, regime uncertainty, and model drift reduce or block position size.
- No profitability guarantee is permitted.

## Completion policy

A development task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded. Operational evidence may not be marked complete until the real elapsed-time run occurs.

## Next action

Confirm the market-feature branch in GitHub Actions, then build a versioned combined PAPER feature vector that joins news, sentiment, macro, filings, and market features without connecting it to real-order execution.
