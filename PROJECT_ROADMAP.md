# AiPro Project Roadmap

Updated: 2026-07-24

## Project goal

Build a safe, maintainable multi-asset automated-trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains remain isolated:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies
- `aipro/intelligence/` — broker-neutral intelligence inputs

Crypto and US-stock capital, broker state, risk limits, approval state, credentials, order IDs, daily baselines, research datasets, and model records must never be combined implicitly.

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

Current milestone completion: **96%**

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
- [x] Fixed-order `paper-feature-vector-v1` schema combining news, macro, filings, and market features
- [x] Required-component, symbol-consistency, future-timestamp, and component-skew eligibility gates
- [x] Source-fingerprint lineage and deterministic combined SHA-256 fingerprint
- [x] Chronological labeled-row contract with schema, width, timestamp, and evidence validation
- [x] Expanding-window walk-forward folds with configurable embargo gaps
- [x] Deterministic ridge baseline and strictly held-out MAE, RMSE, and directional accuracy
- [x] Duplicate-evidence, mixed-schema, insufficient-row, and temporal-order fail-closed gates
- [x] Deterministic reference-versus-current feature-distribution drift detection
- [x] Out-of-sample feature ablation through the existing walk-forward evaluator
- [x] Fingerprinted PAPER model records with immutable IDs and explicit crypto/US-stock isolation
- [x] Risk-adjusted expected value and volatility-based PAPER position sizing
- [x] Deterministic PAPER execution-cost and partial-fill simulation
- [x] Independent crypto and US-stock regime/strategy pipelines
- [x] Classical ML candidate evaluation framework
- [x] Optional isolated gradient-boosting and sequence-model backend registries
- [x] End-to-end domain-isolated PAPER strategy validation with execution-cost edge checks
- [x] Offline regression tests and safety documentation

### Remaining

- [ ] Filing text/XBRL fact extraction, materiality scoring, and historical outcome evaluation
- [ ] Run and retain domain-specific PAPER validation evidence over real elapsed time

## Development boundary

The software development package is complete for V1 and V2, but this does **not** mean real-money trading is approved.

1. Real Upbit order creation remains absent.
2. Alpaca integration accepts only `https://paper-api.alpaca.markets`.
3. Upbit integration calls only `POST /v1/orders/test`, which validates but does not create an order.
4. Email OTP and TOTP grant only a temporary authorization lease; they do not bypass risk or readiness gates.
5. Authorization secrets, SMTP passwords, broker keys, TOTP secrets, and OTP plaintext must never be committed.
6. An OTP, model record, drift report, ablation result, walk-forward report, feature vector, filing event, macro regime, market feature, strategy validation, or recent profit may never bypass a failed safety gate.

## Operational validation still required

- [ ] Configure a dedicated SMTP or transactional-email account and confirm delivery to the owner email.
- [ ] Enroll the TOTP secret in an authenticator application and store recovery material offline.
- [ ] Add actual Alpaca PAPER credentials and run at least 30 calendar days.
- [ ] Collect sufficient sessions and orders while satisfying expectancy, drawdown, daily-loss, freshness, duplicate-order, and reconciliation gates.
- [ ] Add an IP-restricted Upbit key and execute supervised test-order/preflight checks only.
- [ ] Run the Upbit live-data collector with order creation disabled.
- [ ] Review evidence and produce a separate live-readiness decision.

## Mandatory future real-order gates

A future minimal real-order adapter may be considered only after explicit LIVE guards, active two-factor authorization, recent PAPER validation, at least 30 days of qualifying domain-specific PAPER evidence, reconciliation `MATCH`, fresh data, healthy providers, all portfolio risk limits, unique order IDs, successful preflight when supported, inactive kill switch, and an independent live-readiness review all pass simultaneously.

## Investment-intelligence policy

- Expert opinions are timestamped evidence, not direct commands.
- Source weights must be learned from out-of-sample historical accuracy and decay when performance deteriorates.
- News, filings, macro, chart, volume, volatility, liquidity, regime, and portfolio risk must be combined.
- The optimization target is risk-adjusted expected value and controlled drawdown, not maximum aggression.
- Disagreement, stale data, regime uncertainty, model drift, execution cost, and limited liquidity reduce or block position size.
- No profitability guarantee is permitted.

## Completion policy

A development task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded. Operational evidence may not be marked complete until the real elapsed-time run occurs.

## Next action

Run GitHub Actions for the PAPER strategy-validation branch, fix any regression, then implement filing text/XBRL fact extraction and materiality scoring without connecting research output to real-order execution.
