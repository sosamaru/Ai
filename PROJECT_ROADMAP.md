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

Crypto and US-stock capital, broker state, risk limits, approval state, credentials, order IDs, daily baselines, research datasets, model records, candidate rankings, champion decisions, champion histories, and monitoring recommendations must never be combined implicitly.

## V1 foundation status

Overall completion: **100%**

Completed: execution-flow preservation, PAPER defaults, LIVE guards, persistent balances and baselines, HALTED latch, historical replay, Upbit quotation and read-only inspection, duplicate-order and reconciliation controls, guarded Telegram approval flow, normalized news/sentiment inputs, evidence persistence, regression tests, and safety documentation.

## V2 integration status

Development completion: **100% for the approved non-live integration scope**

Completed: email OTP, RFC 6238 TOTP, temporary authorization leases, atomic persistence and audit evidence, Alpaca PAPER-only account/order/reconciliation adapter, 30-day readiness policy, portfolio and execution gates, Upbit `/v1/orders/test` preflight, hard separation from real-order creation, and secret-safe operation documentation.

## V3 intelligence and model-governance status

Current development completion: **98%**

### Completed

- [x] FRED macro observations, normalization, freshness gates, regime snapshots, and fingerprints
- [x] SEC EDGAR submissions and filing-event normalization
- [x] OHLCV validation and deterministic return, volatility, ATR, volume, spread, liquidity, and trend features
- [x] Fixed-order combined feature vectors with lineage and deterministic fingerprints
- [x] Chronological labeled rows, expanding-window walk-forward folds, and embargo gaps
- [x] Deterministic baseline evaluation with held-out MAE, RMSE, and directional accuracy
- [x] Feature-distribution drift detection and out-of-sample feature ablation
- [x] Fingerprinted PAPER model records with crypto/US-stock isolation
- [x] Risk-adjusted expected-value scoring and volatility-based PAPER position sizing
- [x] Deterministic PAPER execution-cost simulator
- [x] Independent domain-isolated regime strategy pipelines
- [x] Classical ML candidate evaluation and deterministic ranking
- [x] Optional isolated gradient-boosting backend specifications
- [x] Optional isolated LSTM, GRU, and Transformer-encoder backend specifications
- [x] Fail-closed PAPER champion selection with score and expected-value margin gates
- [x] Immutable SQLite PAPER champion registry
- [x] Append-only activation, replacement, rollback, and deactivation history
- [x] Per-domain history isolation and deterministic event-chain fingerprints
- [x] Database triggers blocking registry UPDATE and DELETE operations
- [x] PAPER challenger health monitoring and deterministic governance recommendations
- [x] Drift, calibration, expected-value, drawdown, and evidence-sufficiency gates
- [x] Regression tests and safety documentation for the above development scope

### Remaining

- [ ] Filing text/XBRL fact extraction, materiality scoring, and historical outcome evaluation
- [ ] Concrete time-series training runners for optional model backends with purged/embargoed validation
- [ ] Independent crypto and US-stock PAPER strategy evidence collection

## Current implementation result

The model-governance branch now separates candidate evaluation, champion selection, champion registration, and ongoing challenger monitoring into distinct fail-closed stages. Registry events remain explicit and append-only; monitoring decisions never mutate registry state.

The challenger monitor compares domain-specific immutable health snapshots using drift, Brier calibration, cost-aware expected value, drawdown, aggregate score, and observation counts. It can recommend hold, replacement review, rollback review, deactivation, or abstention. Non-positive expected value and excessive drawdown take priority over challenger performance.

## Known limitations

- The selector, registry, and monitor consume completed evaluation evidence; they do not train, persist, or serve model binaries.
- Monitoring recommendations do not automatically activate, replace, roll back, or deactivate registry entries.
- Registry approval does not authorize inference, broker access, PAPER orders, or LIVE orders.
- Optional deep-learning and boosting packages remain lazily loaded research dependencies.
- GitHub Actions branch confirmation remains required.
- No profitability guarantee is permitted.
- Real Upbit order creation remains absent, and Alpaca remains PAPER-domain only.

## Operational validation still required

- [ ] Configure and verify dedicated SMTP delivery
- [ ] Enroll TOTP and store recovery material offline
- [ ] Run actual Alpaca PAPER credentials for at least 30 calendar days
- [ ] Collect sufficient sessions/orders while all expectancy, drawdown, loss, freshness, duplicate, and reconciliation gates pass
- [ ] Run supervised Upbit inspection and test-order preflight with real order creation disabled
- [ ] Produce a separate live-readiness decision from immutable evidence

## Mandatory future real-order gates

A future minimal real-order adapter may be considered only after explicit LIVE guards, active two-factor authorization, recent domain-specific PAPER validation, at least 30 days of qualifying evidence, reconciliation `MATCH`, fresh data, healthy providers, all portfolio risk limits, unique order IDs, successful preflight when supported, inactive kill switch, and an independent live-readiness review all pass simultaneously.

## Completion policy

A development task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded. Operational evidence may not be marked complete until the real elapsed-time run occurs.

## Next priority

Run branch CI and review the complete model-governance suite. After CI passes, implement immutable monitoring-decision persistence and operator acknowledgement evidence, still without automatic registry mutation or any connection to real-order execution.
