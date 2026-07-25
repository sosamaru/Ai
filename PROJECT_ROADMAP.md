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
- `aipro/research/` — leakage-safe PAPER research and validation

Crypto and US-stock capital, broker state, risk limits, approval state, credentials, order IDs, daily baselines, datasets, folds, model records, candidate rankings, and governance evidence must never be combined implicitly.

## V1 foundation status

Overall completion: **100%**

Completed: execution-flow preservation, PAPER defaults, LIVE guards, persistent balances and baselines, HALTED latch, historical replay, Upbit quotation and read-only inspection, duplicate-order and reconciliation controls, guarded Telegram approval flow, normalized news/sentiment inputs, evidence persistence, regression tests, and safety documentation.

## V2 integration status

Development completion: **100% for the approved non-live integration scope**

Completed: email OTP, RFC 6238 TOTP, temporary authorization leases, atomic persistence and audit evidence, Alpaca PAPER-only account/order/reconciliation adapter, 30-day readiness policy, portfolio and execution gates, Upbit `/v1/orders/test` preflight, hard separation from real-order creation, and secret-safe operation documentation.

## V3 intelligence, validation, and model-governance status

Current construction completion: **99% across active companion branches, pending final CI and integration**

### Completed on main or active reviewed branches

- [x] FRED macro observations, SEC EDGAR filing events, OHLCV validation, and deterministic fingerprints
- [x] Fixed-order combined feature vectors with lineage and freshness gates
- [x] Chronological labeled rows and baseline walk-forward evaluation
- [x] Feature drift detection, feature ablation, and PAPER model records
- [x] Risk-adjusted expected-value scoring and volatility-based PAPER sizing
- [x] Deterministic PAPER execution-cost simulation
- [x] Independent crypto and US-stock regime strategy pipelines
- [x] Classical ML candidate evaluation and deterministic ranking
- [x] Optional isolated gradient-boosting and sequence-model backend specifications
- [x] Purged walk-forward splitter with overlapping-label removal and post-test embargo evidence
- [x] Deterministic dependency-free logistic PAPER training runner using purged folds
- [x] Training-only feature scaling and untouched held-out fold scoring
- [x] Balanced accuracy, Brier calibration, cost-aware expected value, turnover, and sample evidence
- [x] Deterministic fold, model, candidate-evaluation, and report SHA-256 fingerprints
- [x] Strict crypto/US-stock research isolation
- [x] Companion model champion selection, immutable registry, challenger monitoring, operator approval, and explicit PAPER command boundary
- [x] Regression tests and safety documentation for the above construction scope

### Remaining construction

- [ ] Merge and CI-confirm the purged validation/training branch and model-governance branch together
- [ ] Add bounded training adapters for optional boosting and sequence backends using the same purged fold contract
- [ ] Filing text/XBRL fact extraction, materiality scoring, and historical outcome evaluation
- [ ] Produce a completion manifest comparing code, tests, documentation, and roadmap claims

### Operational evidence still required

- [ ] Configure and verify dedicated SMTP delivery
- [ ] Enroll TOTP and store recovery material offline
- [ ] Run actual Alpaca PAPER credentials for at least 30 calendar days
- [ ] Collect independent crypto and US-stock sessions/orders while expectancy, drawdown, loss, freshness, duplicate, and reconciliation gates pass
- [ ] Run supervised Upbit inspection and test-order preflight with real order creation disabled
- [ ] Produce a separate live-readiness decision from immutable evidence

## Current implementation result

The purged training branch now provides a concrete end-to-end research path from validated time-ordered rows to leakage-controlled folds, bounded model fitting, untouched test scoring, and the existing candidate-evaluation gate. Scaling statistics are calculated from each training fold only. Overlapping label windows are removed before fitting, and post-test embargo indices are recorded.

The output remains PAPER research evidence. It does not persist or serve model binaries, mutate champion state, contact brokers, submit orders, enable LIVE mode, or bypass any risk or authorization control.

## Known limitations

- The first concrete runner supports a deterministic binary logistic baseline only.
- Optional boosting and deep-learning packages remain lazily loaded and do not yet have concrete purged training adapters.
- GitHub Actions must confirm the latest branch commit before this construction item is marked integrated.
- Companion PRs must be rebased or merged carefully because they started from the same earlier `main` commit.
- No profitability guarantee is permitted.
- Real Upbit order creation remains absent, and Alpaca remains PAPER-domain only.

## Mandatory future real-order gates

A future minimal real-order adapter may be considered only after explicit LIVE guards, active two-factor authorization, recent domain-specific PAPER validation, at least 30 days of qualifying evidence, reconciliation `MATCH`, fresh data, healthy providers, all portfolio risk limits, unique order IDs, successful preflight when supported, inactive kill switch, and an independent live-readiness review all pass simultaneously.

## Completion policy

A development task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded. Operational evidence may not be marked complete until the real elapsed-time run occurs.

## Next priority

Run full branch CI. If it passes, integrate the purged training branch with the model-governance branch, then implement a bounded optional gradient-boosting training adapter that consumes the same purged fold evidence without changing `run.py -> telegram.py -> main.py -> TradingApplication`.
