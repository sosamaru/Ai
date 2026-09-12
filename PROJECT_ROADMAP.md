# AiPro Project Roadmap

Updated: 2026-09-12

## Current owner requirement — US dual portfolio

Latest source inspected: `main` at `6be27da5e8ba64d3f1ae162855b05c06f063c3bb` (PR #74 is already merged; the old next-priority paragraph below is superseded).

New construction scope: an executable US-stock PAPER portfolio with KRW 200,000 for intraday trading and KRW 800,000 for long-term holdings. Lifetime external funding is capped at KRW 1,000,000; only proceeds earned inside each sleeve may be reinvested. No borrowing, leverage, or implicit transfers from crypto or between sleeves. The requested 2% daily return is a short-sleeve profit-stop target, not a forecast or guarantee.

At inspection, the canonical entrypoint constructs the crypto application. US-stock adapters and research components exist, but this dual portfolio and its runtime wiring are missing. Historical V1–V3 percentages below refer only to their stated construction scopes and do not describe this new requirement or a complete profitable trading service.

New-scope completion: **8/8 verified deliverables (100%; remaining 0%)** for the local PAPER construction scope. Overall LIVE-service completion is not represented by this denominator. Implementation is on `feat/us-dual-capital-20260912`, pending review and remote CI; it is not yet merged into main.

- [x] Fixed funding boundary and persistent isolated sleeve accounting.
- [x] Cost/FX-aware fills, settled cash, and restart-safe atomic execution.
- [x] Intraday momentum and slow long-term trend strategies.
- [x] Existing market-feature, regime, and optional forecast/EV integration.
- [x] Profit-stop, loss-stop, drawdown, stale-data, and exposure gates.
- [x] Canonical runtime, authenticated controls, and bounded continuous PAPER execution.
- [x] Reproducible demo and chronological replay with honest evidence labels.
- [x] Regression validation, usage guide, and synchronized completion record.

Verification on 2026-09-12 (Linux, Python 3.12.14): baseline 436 tests passed. After implementation, `python -m aipro all` passed environment diagnosis, compilation, canonical PAPER smoke, 70 integration tests, and **483 warning-free regression tests**. The new portfolio/combined-feature group passed 52 tests. Deterministic synthetic replay completed 4 frames and 3 virtual fills, with no blocked frames; it is not performance or elapsed-time evidence. Remote Python 3.11–3.13 CI is pending until the PR runs.

| Delivery scope | Completion | Remaining reason |
|---|---|---|
| Local dual-portfolio PAPER construction | 8/8, 100% | None within this explicitly bounded scope |
| This profile’s actual brokerage/data integration | 0/1, 0% | Broker, account constraints and providers not confirmed |
| Supplied fitted model validated for this profile | 0 validated candidates | Historical dataset, training and out-of-sample evidence missing |
| Actual elapsed PAPER evidence for this profile | 0/30 required calendar days, 0% | Synthetic replay is excluded |
| Complete real-money trading service | Not complete; percentage not yet measurable | Broker-dependent scope, corporate actions, real-account reconciliation and LIVE review unresolved |

Reason the overall trading service remains incomplete: no real market-data/broker adapter is wired into this new runtime; fitted-model inference is opt-in and no trained model is supplied; corporate-action/dividend/tax accounting and real USD account reconciliation remain to implement; actual long-duration PAPER evidence and profitability validation do not exist for this profile. Next priority: confirm the user's brokerage and data source, implement those missing accounting/integration requirements, then collect actual PAPER evidence. No extra owner funding is allowed.

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

Completed: execution-flow preservation, PAPER defaults, LIVE guards, persistent balances and baselines, HALTED latch, historical replay, Upbit quotation and read-only inspection, duplicate-order and reconciliation controls, guarded Telegram approval flow, guarded snapshot-to-PAPER comparison, normalized news/sentiment inputs, evidence persistence, regression tests, and safety documentation.

## V2 integration status

Development completion: **100% for the approved non-live integration scope**

Completed: email OTP, RFC 6238 TOTP, temporary authorization leases, atomic persistence and audit evidence, Alpaca PAPER-only account/order/reconciliation adapter, 30-day readiness policy, portfolio and execution gates, Upbit `/v1/orders/test` preflight, hard separation from real-order creation, and secret-safe operation documentation.

## V3 intelligence, validation, and model-governance status

Current construction completion: **100% integrated on main for the approved PAPER/non-live scope**

### Completed and integrated on main

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
- [x] Explicit CIK-scoped reviewed SEC concept aliases with unit gates, collision rejection, deterministic evidence, and opt-in canonical comparisons
- [x] Deterministic filing materiality scoring from forms, items, reviewed phrases, and XBRL changes
- [x] Historical filing outcome evaluation with optional timestamp-aligned benchmark abnormal returns
- [x] Deterministic Completion Manifest comparing code, tests, documentation, roadmap markers, limitations, and operational evidence boundaries
- [x] Dedicated regression test for `run.py -> telegram.py -> main.py -> TradingApplication`
- [x] Safe `.env.example`, repository security policy, regression tests, and documentation for the approved construction scope
- [x] Complete dependency-free GitHub Actions workflow passed on PR #62 before merge
- [x] Complete dependency-free GitHub Actions workflow passed on PR #71 before merge
- [x] Completion Manifest integrated into `main`
- [x] Deterministic operational-readiness ZIP export with explicit `execution_authority: false`
- [x] Database-independent, fail-closed offline verifier for archive structure, canonical content, fingerprints, evidence semantics, and Markdown consistency
- [x] Guarded read-only Upbit snapshot-to-PAPER comparison runner merged from PR #30 after successful CI
- [x] Conflict-safe persistent crypto approval evidence added without replacing the existing compatibility API

### Development construction status

No remaining code-only construction item is recorded for the approved PAPER/non-live scope. New development must begin from a separately reviewed requirement and must not be presented as operational or LIVE readiness.

Issue #70 separately reviewed the SEC concept-alias extension. It adds an explicit opt-in intelligence path only: aliases are scoped to one CIK, require reviewer evidence and approved units, reject ambiguity and canonical collisions, and never use automatic semantic inference.

Separately reviewed operational-support requirements now include supervised SMTP and TOTP verification runners, an Alpaca PAPER readiness monitor, an operational readiness review bundle, a deterministic offline export package, and a database-independent offline verifier. These workflows combine source fingerprints and hashed manual attestations into fail-closed evidence without granting trading authority.

### Merge consolidation completed on 2026-07-30

- PR #30 was merged after its complete dependency-free test workflow succeeded.
- The useful PR #32 approval-state behavior was re-integrated as `aipro/crypto/persistent_live_approval.py` so the current `aipro/crypto/live_approval.py` API remains intact.
- The persistent approval store validates state, timezone-aware timestamps, SHA-256 evidence, operator identity continuity, readiness continuity, HALTED state, expiry, and the explicit environment guard.
- Approval audit records are append-only and protected against UPDATE and DELETE.
- Stale foundation PRs that are already superseded by current `main` are closed rather than force-merged, preventing regression of code, documentation, completion status, and safety gates.
- PR #72 passed the complete repository test workflow before merge.
- No real-order endpoint, broker mutation, LIVE authorization grant, or domain-state mixing was introduced.

### Professional runtime and compatibility audit on 2026-07-30

Audit branch: `fix/professional-runtime-audit-20260730`, based on the latest `main` after PR #72.

- [x] Added dependency-free local `.env` loading before application construction while preserving injected process-environment precedence.
- [x] Added fail-closed validation for non-positive cash/order settings, order size above initial cash, unsupported log levels, and non-finite risk or market-data limits.
- [x] Serialized the legacy-compatible crypto market-health wrapper so concurrent status and cycle calls cannot create self-delegation or restore the wrong provider.
- [x] Added bounded SQLite busy handling and `BEGIN IMMEDIATE` atomicity for persistent crypto approval state transitions.
- [x] Standardized SQLite transaction and connection lifetime across runtime, evidence, governance, readiness, and test stores; direct `sqlite3.connect()` use is rejected by a repository contract test.
- [x] Hardened Telegram JSON object, update-list, and update-ID validation so malformed provider responses cannot corrupt polling state.
- [x] Removed the existing invalid-regex-escape warning and configured tests to fail on any warning.
- [x] Expanded CI compatibility coverage to Python 3.11, 3.12, and 3.13 with source/test compilation and a full `python run.py` PAPER smoke execution.
- [x] Added deterministic regression tests for `.env` parsing, invalid configuration, concurrent market-health access, malformed Telegram updates, approval-database contention, and SQLite resource lifetime.
- [x] Recorded findings, corrections, validation contract, merge policy, and remaining limitations in `docs/PROFESSIONAL_RUNTIME_AUDIT.md`.
- [x] PR #73 completed the warning-free Python 3.11–3.13 matrix: compilation, full PAPER entrypoint smoke execution, and 432 regression tests passed on every version.

This audit improves runtime reliability, merge confidence, and compatibility evidence. It does not create real-order capability, prove profitability, or satisfy external operational evidence requirements.

### Execution recovery and explicit integration validation on 2026-07-31

Implementation branch: `fix/execution-integration-runner-20260731`; validation record: PR #74.

Code construction completion: **100% for the reviewed execution-recovery scope**

- [x] Added `python -m aipro doctor` to identify unsupported Python, missing entrypoints/imports, invalid `.env` or process configuration, unwritable DB/log paths, and missing pytest.
- [x] Added explicit `compile`, `smoke`, `integration`, `test`, `all`, and canonical `run` commands under one cross-platform module entrypoint.
- [x] Added an isolated deterministic PAPER smoke test using DEMO data, temporary DB/log paths, blank Telegram credentials, and disabled LIVE guards.
- [x] Added a separately executable concrete integration group instead of relying only on indirect coverage inside the complete suite.
- [x] Added Windows Command Prompt and PowerShell launchers that select Python 3.13, 3.12, or 3.11 and return the underlying process exit code.
- [x] Added a manually runnable GitHub Actions workflow with validation-target and Python-version selection plus retained logs.
- [x] Expanded normal CI into visible diagnosis, compilation, canonical PAPER execution, integration, and complete warning-free regression stages.
- [x] Added CLI regression tests, README commands, and `docs/EXECUTION_RUNBOOK.md` failure-recovery guidance.
- [x] Preserved `run.py -> telegram.py -> main.py -> TradingApplication` and kept crypto/U.S.-stock state isolated.

Validation and merge policy:

- PR #74 must not merge unless the Python 3.11, 3.12, and 3.13 matrix passes every explicit stage.
- A repository CI pass proves the clean GitHub runner path only. The user's Windows machine must still run `aipro.cmd doctor --require-pytest` followed by `aipro.cmd all` to identify machine-specific Python, permission, antivirus, firewall, DNS, proxy, credential, or provider failures.
- Missing SMTP/TOTP credentials, missing 30-day Alpaca PAPER evidence, and missing supervised Upbit evidence remain operational blockers rather than core execution-code failures.
- No real-order endpoint, LIVE authority, profitability claim, or risk bypass is introduced by the execution runner.

Reason the previous state appeared unusable:

- the existing Actions workflow had no `workflow_dispatch`, so GitHub could not expose a manual Run workflow control;
- local commands were fragmented and did not identify which prerequisite or stage failed;
- integration coverage existed inside the full suite but was not separately runnable or visible;
- no repository Windows launcher consistently selected a supported Python runtime.

Next priority for this scope: obtain successful PR #74 matrix evidence, merge only after success, then run the unified Windows diagnostics on the actual operating machine and record any remaining machine-specific blocker without falsely changing operational-readiness status.

### Operational evidence still required

- [ ] Configure and verify dedicated SMTP delivery
- [ ] Enroll TOTP and store recovery material offline
- [ ] Run actual Alpaca PAPER credentials for at least 30 calendar days
- [ ] Collect independent crypto and US-stock sessions/orders while expectancy, drawdown, loss, freshness, duplicate, and reconciliation gates pass
- [ ] Run supervised Upbit inspection and test-order preflight with real order creation disabled
- [ ] Produce a separate live-readiness decision from immutable evidence

The SMTP verification implementation is not operational completion. The checkbox remains open until owner-controlled credentials are used, the provider accepts delivery, and mailbox arrival is manually confirmed.

The TOTP verification implementation is not operational completion. The checkbox remains open until the owner enrolls the actual secret in an authenticator, successfully verifies a current code, and confirms that recovery material is stored offline.

The Alpaca PAPER readiness monitor is not 30-day operational completion. It automates evidence collection and fail-closed assessment, but only real owner-controlled PAPER credentials and actual elapsed calendar time may satisfy the duration requirement.

The operational readiness review bundle is not a live-readiness decision. It only proves that the required evidence inputs are present and qualifying enough to be handed to an independent reviewer.

The offline export and verifier prove internal package consistency only. They do not authenticate the archive creator, validate the truth of manual attestations, satisfy elapsed-time requirements, or produce `LIVE_READY`.

## Current implementation result

The research path now moves from validated time-ordered observations through purged/embargoed folds, bounded fitting, untouched scoring, candidate evaluation, champion governance, regime strategy selection, cost-aware sizing, and deterministic PAPER execution validation.

The optional boosting runner constructs a fresh explicitly requested estimator for every fold. XGBoost, LightGBM, and CatBoost remain lazy optional dependencies. Unknown parameters, excessive training budgets, parallel execution, mixed domains, invalid seeds, malformed probabilities, and leakage evidence fail closed.

The optional sequence runner constructs a fresh LSTM, GRU, or Transformer encoder for every fold. PyTorch and TensorFlow remain lazy optional dependencies. A sequence window must be contiguous and wholly contained in its train or test partition, scaling statistics come only from training sequences, and model training remains bounded by the reviewed architecture and per-fold materialization limits.

The SEC analysis path accepts an existing normalized filing event, bounded public filing HTML, Company Facts evidence for the same CIK, and optional externally supplied price observations. It extracts visible text, accession-matched XBRL facts, deterministic prior-period comparisons, materiality reasons, and historical raw or benchmark-adjusted outcomes without contacting a broker or creating a strategy instruction.

The alias-aware SEC path is separate and explicit. It canonicalizes current and historical facts only through a reviewed CIK-scoped registry, records rule and application fingerprints, allows only approved units, and fails closed on duplicate sources, transitive mappings, registry tampering, CIK mismatch, or conflicting canonical facts. Automatic name similarity, embeddings, or LLM-generated accounting mappings remain prohibited.

The Completion Manifest evaluates reviewed development claims against real repository files, SHA-256 file evidence, regression tests, documentation, and exact roadmap markers. Missing paths, missing markers, unsafe paths, and duplicate identifiers fail closed. Real elapsed-time or credential-backed operational evidence is deliberately kept separate and cannot be marked complete by source-code inspection.

The SMTP operational runner requires the exact `AIPRO_SMTP_VERIFY=YES` opt-in, hashes the recipient before persistence, omits OTP plaintext and exception messages, records success or failure in an append-only SQLite store, and returns a failing process status when delivery is not accepted.

The TOTP operational runner requires the exact `AIPRO_TOTP_VERIFY=YES` opt-in, receives the current code through a hidden prompt, stores only an enrollment-label hash and time counter, rejects accepted-counter reuse, and records append-only accepted or rejected evidence without persisting the TOTP secret or code.

The Alpaca PAPER readiness runner requires exact `AIPRO_ALPACA_PAPER_VERIFY=YES`, accepts only the official PAPER API client, appends raw account/order snapshots, derives a deterministic readiness report, and returns a failing status until every configured evidence gate passes.

The operational readiness review carries forward source fingerprints, stores only hashed operator labels and notes, fails closed when any source is missing, and never produces `LIVE_READY`.

The deterministic export packages the latest readiness review as canonical JSON, human-readable Markdown, and a manifest with fixed ZIP metadata and explicit non-execution authority. The offline verifier reads no source database, extracts no files to disk, enforces bounded archive structure, recomputes all version-1 fingerprints, checks evidence/blocker semantics, and rejects any inconsistent human-readable summary.

The guarded snapshot comparison runner requires explicit opt-in, reads only the latest immutable Upbit snapshot and a supplied PAPER observation, validates timestamps, non-negative balances, and unique order IDs, and persists redacted append-only comparison evidence without mutating either account.

The persistent approval evidence store records the guarded crypto approval sequence in an isolated SQLite database while preserving the existing compatibility state machine. It rechecks readiness, operator identity, expiry, HALTED, and environment guards at each relevant transition and cannot authorize the US-stock domain or any order adapter.

All outputs remain PAPER research, governance, operational-support, or repository-integrity evidence. They do not submit real orders, enable LIVE mode, automatically mutate champion state, or bypass risk, authorization, reconciliation, HALTED, or kill-switch controls.

## Known limitations

- Optional PyTorch and TensorFlow packages are not installed in core CI; dependency-free tests validate orchestration through deterministic fake trainers, while real backend execution requires an explicitly provisioned research environment.
- Boosting and sequence model binaries are not persisted or served; only deterministic PAPER evaluation evidence is produced.
- Filing materiality is a reviewed deterministic heuristic, not a recommendation or profitability forecast.
- Company Facts aliasing is explicit and CIK-scoped only; the system does not automatically infer semantic equivalence, resolve dimensional contexts, or prove that a reviewed accounting mapping is correct.
- Historical outcomes require externally supplied, timestamp-aligned price data and do not contact a market-data provider.
- Confirmed governance commands do not automatically mutate the champion registry.
- Completion Manifest success proves repository traceability for the approved construction scope only; it does not prove operational readiness, live safety, or profitability.
- SMTP server acceptance does not prove mailbox arrival; supervised manual confirmation is still required.
- A valid TOTP code does not prove that recovery material is safely stored or that the operator device remains secure.
- PAPER monitor test fixtures do not count toward the real 30-calendar-day requirement.
- Manual attestations are statements by the operator and require independent review; hashes prove record continuity, not truth.
- SHA-256 package verification proves integrity but not signer identity; no detached digital-signature or trusted-key lifecycle is implemented.
- The core CI does not install optional third-party boosting or deep-learning binaries; real backend compatibility remains a separately provisioned research-environment responsibility.
- No profitability guarantee is permitted.
- Real Upbit order creation remains absent, and Alpaca remains PAPER-domain only.
- Repository CI cannot prove a specific Windows machine's Python registration, file permissions, antivirus rules, firewall, DNS, proxy, API credentials, or provider reachability; use the unified local diagnostic commands for that evidence.

## Mandatory future real-order gates

A future minimal real-order adapter may be considered only after explicit LIVE guards, active two-factor authorization, recent domain-specific PAPER validation, at least 30 days of qualifying evidence, reconciliation `MATCH`, fresh data, healthy providers, all portfolio risk limits, unique order IDs, successful preflight when supported, inactive kill switch, and an independent live-readiness review all pass simultaneously.

## Completion policy

A development task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded. Operational evidence may not be marked complete until the real elapsed-time run occurs.

## Next priority

PR #74 is already merged. Review the new US dual-portfolio branch and its Python 3.11–3.13 CI results. Confirm the owner’s actual US-stock brokerage and data source, then implement the USD-account/settlement integration, corporate-action and dividend/tax accounting, and input acquisition described in `docs/US_DUAL_PORTFOLIO.md`. Validate the baseline and fitted candidates with point-in-time historical data before collecting at least 30 calendar days of actual qualifying broker PAPER evidence. Keep the existing SMTP/TOTP and other mandatory live-readiness gates intact. Keep all development on branches based on latest main; no real-money order activation or additional owner contributions are part of this change.
