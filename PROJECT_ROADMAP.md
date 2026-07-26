# AiPro Project Roadmap

Updated: 2026-07-25

## Project goal

Build a safe, maintainable multi-asset automated-trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains remain isolated:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies
- `aipro/intelligence/` — broker-neutral intelligence inputs and governance
- `aipro/research/` — leakage-safe PAPER research and validation

Crypto and US-stock capital, broker state, risk limits, credentials, order IDs, daily baselines, datasets, folds, model records, candidate rankings, champion state, governance evidence, and validation reports must never be combined implicitly.

## V1 foundation status

Overall completion: **100%**

Completed: execution-flow preservation, PAPER defaults, LIVE guards, persistent balances and baselines, HALTED latch, historical replay, Upbit quotation and read-only inspection, duplicate-order and reconciliation controls, guarded Telegram approval flow, normalized news/sentiment inputs, evidence persistence, regression tests, and safety documentation.

## V2 integration status

Development completion: **100% for the approved non-live integration scope**

Completed: email OTP, RFC 6238 TOTP, temporary authorization leases, atomic persistence and audit evidence, Alpaca PAPER-only account/order/reconciliation adapter, 30-day readiness policy, portfolio and execution gates, Upbit `/v1/orders/test` preflight, hard separation from real-order creation, and secret-safe operation documentation.

## V3 intelligence, validation, and model-governance status

Current construction completion: **99%**

### Completed on main or the current reviewed branch

- [x] FRED macro observations, SEC EDGAR filing events, OHLCV validation, and deterministic fingerprints
- [x] Fixed-order combined feature vectors with lineage and freshness gates
- [x] Chronological labeled rows and baseline walk-forward evaluation
- [x] Feature drift detection, feature ablation, and PAPER model records
- [x] Risk-adjusted expected-value scoring and volatility-based PAPER sizing
- [x] Deterministic PAPER execution-cost and partial-fill simulation
- [x] Independent crypto and US-stock regime strategy pipelines
- [x] Classical ML candidate evaluation and deterministic ranking
- [x] Optional isolated gradient-boosting and sequence-model backend specifications
- [x] Purged walk-forward validation with overlapping-label removal and post-test embargo evidence
- [x] Deterministic dependency-free logistic PAPER training runner using purged folds
- [x] Bounded lazy XGBoost, LightGBM, and CatBoost training adapters using the same purged-fold contract
- [x] Per-fold estimator isolation and untouched held-out probability scoring
- [x] Training-only scaling where required and untouched held-out fold scoring
- [x] Balanced accuracy, Brier calibration, cost-aware expected value, turnover, and sample evidence
- [x] Deterministic fold, model, candidate-evaluation, report, and governance SHA-256 fingerprints
- [x] Strict crypto/US-stock research and governance isolation
- [x] Fail-closed PAPER champion selection with score and expected-value margin gates
- [x] Immutable SQLite PAPER champion registry with append-only activation, replacement, rollback, and deactivation history
- [x] Challenger health monitoring with drift, calibration, expected-value, drawdown, and evidence-sufficiency gates
- [x] Immutable PAPER operator-review approval ledger and explicit non-execution-authority markers
- [x] PAPER governance command proposals with exact confirmation phrase and no automatic registry mutation
- [x] End-to-end domain-isolated PAPER strategy validation combining regime selection, EV sizing, and execution simulation
- [x] Fail-closed rejection of abstention, provider outage, invalid lineage, partial fills, and execution-cost-eroded edge
- [x] Regression tests and safety documentation for the integrated construction scope

### Remaining construction

- [ ] Confirm the latest integrated `main` commit and this branch in GitHub Actions
- [ ] Add bounded purged-fold training adapters for optional sequence backends
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

The research path now moves from validated time-ordered observations through purged/embargoed folds, bounded fitting, untouched scoring, candidate evaluation, champion governance, regime strategy selection, cost-aware sizing, and deterministic PAPER execution validation.

The optional boosting runner constructs a fresh explicitly requested estimator for every fold. XGBoost, LightGBM, and CatBoost remain lazy optional dependencies. Unknown parameters, excessive training budgets, parallel execution, mixed domains, invalid seeds, malformed probabilities, and leakage evidence fail closed.

All outputs remain PAPER research or governance evidence. They do not contact brokers, submit real orders, enable LIVE mode, automatically mutate champion state, or bypass risk, authorization, reconciliation, HALTED, or kill-switch controls.

## Known limitations

- Optional sequence-model packages remain lazily loaded and do not yet have concrete purged training adapters.
- Boosting model binaries are not persisted or served; only deterministic PAPER evaluation evidence is produced.
- Confirmed governance commands do not automatically mutate the champion registry.
- The newest branch must pass GitHub Actions before merge.
- No profitability guarantee is permitted.
- Real Upbit order creation remains absent, and Alpaca remains PAPER-domain only.

## Mandatory future real-order gates

A future minimal real-order adapter may be considered only after explicit LIVE guards, active two-factor authorization, recent domain-specific PAPER validation, at least 30 days of qualifying evidence, reconciliation `MATCH`, fresh data, healthy providers, all portfolio risk limits, unique order IDs, successful preflight when supported, inactive kill switch, and an independent live-readiness review all pass simultaneously.

## Completion policy

A development task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded. Operational evidence may not be marked complete until the real elapsed-time run occurs.

## Next priority

Run full GitHub Actions on this branch. After it passes, merge the bounded boosting adapter and implement a bounded optional sequence-model training adapter using the same purged-fold evidence contract while keeping dependencies lazy, artifacts PAPER-only, domains isolated, and `run.py -> telegram.py -> main.py -> TradingApplication` unchanged.
