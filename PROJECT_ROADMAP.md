# AiPro Project Roadmap

Updated: 2026-07-26

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

Current construction completion: **100% on the current reviewed branch, pending GitHub Actions and merge**

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
- [x] Bounded lazy PyTorch and TensorFlow LSTM, GRU, and Transformer-encoder training adapters using the same purged-fold contract
- [x] Fresh per-fold estimator/model isolation and untouched held-out probability scoring
- [x] Training-only scaling and strict partition-local contiguous sequence construction
- [x] Per-fold sequence-count and materialized-feature-value resource ceilings
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
- [x] Bounded SEC filing HTML extraction with executable-content exclusion and deterministic evidence
- [x] SEC Company Facts extraction with accession/form matching and prior-period comparisons
- [x] Deterministic filing materiality scoring from forms, items, reviewed phrases, and XBRL changes
- [x] Historical filing outcome evaluation with optional timestamp-aligned benchmark abnormal returns
- [x] Deterministic Completion Manifest comparing code, tests, documentation, roadmap markers, limitations, and operational evidence boundaries
- [x] Dedicated regression test for `run.py -> telegram.py -> main.py -> TradingApplication`
- [x] Regression tests and safety documentation for the approved construction scope

### Remaining construction gate

- [ ] Run the complete GitHub Actions workflow on the Completion Manifest branch and merge it into `main`

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

The optional sequence runner constructs a fresh LSTM, GRU, or Transformer encoder for every fold. PyTorch and TensorFlow remain lazy optional dependencies. A sequence window must be contiguous and wholly contained in its train or test partition, scaling statistics come only from training sequences, and model training remains bounded by the reviewed architecture and per-fold materialization limits.

The SEC analysis path accepts an existing normalized filing event, bounded public filing HTML, Company Facts evidence for the same CIK, and optional externally supplied price observations. It extracts visible text, accession-matched XBRL facts, deterministic prior-period comparisons, materiality reasons, and historical raw or benchmark-adjusted outcomes without contacting a broker or creating a strategy instruction.

The Completion Manifest now evaluates reviewed development claims against real repository files, SHA-256 file evidence, regression tests, documentation, and exact roadmap markers. Missing paths, missing markers, unsafe paths, and duplicate identifiers fail closed. Real elapsed-time or credential-backed operational evidence is deliberately kept separate and cannot be marked complete by source-code inspection.

All outputs remain PAPER research, governance, or repository-integrity evidence. They do not submit real orders, enable LIVE mode, automatically mutate champion state, or bypass risk, authorization, reconciliation, HALTED, or kill-switch controls.

## Known limitations

- Optional PyTorch and TensorFlow packages are not installed in core CI; dependency-free tests validate orchestration through deterministic fake trainers, while real backend execution requires an explicitly provisioned research environment.
- Boosting and sequence model binaries are not persisted or served; only deterministic PAPER evaluation evidence is produced.
- Filing materiality is a reviewed deterministic heuristic, not a recommendation or profitability forecast.
- Company Facts comparisons depend on SEC taxonomy consistency and do not yet perform semantic concept aliasing across issuer-specific extensions.
- Historical outcomes require externally supplied, timestamp-aligned price data and do not contact a market-data provider.
- Confirmed governance commands do not automatically mutate the champion registry.
- Completion Manifest success proves repository traceability for the approved construction scope only; it does not prove operational readiness, live safety, or profitability.
- The current Completion Manifest branch must pass GitHub Actions before merge; the merged `main` push workflow still requires separate confirmation.
- No profitability guarantee is permitted.
- Real Upbit order creation remains absent, and Alpaca remains PAPER-domain only.

## Mandatory future real-order gates

A future minimal real-order adapter may be considered only after explicit LIVE guards, active two-factor authorization, recent domain-specific PAPER validation, at least 30 days of qualifying evidence, reconciliation `MATCH`, fresh data, healthy providers, all portfolio risk limits, unique order IDs, successful preflight when supported, inactive kill switch, and an independent live-readiness review all pass simultaneously.

## Completion policy

A development task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded. Operational evidence may not be marked complete until the real elapsed-time run occurs.

## Next priority

Run the complete GitHub Actions workflow on the Completion Manifest branch and merge it. After merge, development construction for the approved PAPER/non-live scope is complete. The next work is operational evidence collection, beginning with dedicated SMTP verification and TOTP enrollment, followed by the required 30-calendar-day Alpaca PAPER observation period. None of those external requirements may be marked complete from code or documentation alone.
