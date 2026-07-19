# AiPro Project Roadmap

Updated: 2026-07-19

## Project goal

Build a safe, maintainable multi-asset automated trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Asset domains remain isolated:

- `aipro/core/` — asset-neutral contracts and safety boundaries
- `aipro/crypto/` — crypto-specific configuration, adapters, and strategies
- `aipro/us_stocks/` — US-stock-specific configuration, adapters, and strategies

Development order:

1. Offline tests
2. Backtesting
3. Paper trading
4. Live-readiness review
5. Explicitly approved live trading

Each asset domain must pass this sequence independently. Capital, broker state, risk limits, order IDs, approval state, credentials, and daily performance baselines must never be shared implicitly between crypto and US stocks.

## Portfolio baseline policy

1. Crypto and US-stock portfolios maintain independent daily baselines.
2. Crypto daily baseline = crypto cash + current market value of crypto holdings.
3. US-stock daily baseline = US-stock cash + current market value of US-stock holdings.
4. Each baseline resets once per day from that domain's current account value and is used only for that domain's daily return and risk calculations.
5. A combined total may be displayed for reporting but never replaces either independent baseline.
6. The US-stock policy reserves approximately KRW 200,000 for its domain, with a separate high-volatility momentum allocation.

## Current status

Overall completion: **88%**

### Completed

- [x] Entry-point structure and crypto runtime ownership through `aipro/crypto/application.py`
- [x] PAPER default and double LIVE guard
- [x] Persistent KST trading date, independent crypto/US-stock baselines, and HALTED latch
- [x] Persistent PAPER cash, positions, average prices, immutable order IDs, and interrupted-cycle recovery
- [x] Read-only reconciliation and bounded broker retry policy
- [x] Deterministic historical replay with fees, slippage, sizing, drawdown, win rate, exposure, and reports
- [x] Strict CSV historical-data loader with schema validation and SHA-256 fingerprinting
- [x] Independent PAPER-readiness PASS/FAIL reports
- [x] Immutable completed-order archive with duplicate-ID protection and restart recovery
- [x] Disabled-by-default US-stock domain and separate namespace/capital policy
- [x] Upbit unauthenticated read-only quotation adapter
- [x] Validated ticker/candle momentum, volatility, and source timestamps
- [x] Market-data latency, source-age, failure-count, and fail-closed execution gate
- [x] Isolated authenticated Upbit read-only account client
- [x] Secret-safe credential loading and GET-only account/order inspection
- [x] Network-level blocking of non-read-only private endpoints
- [x] Guarded supervised read-only verification with redacted JSON evidence
- [x] Immutable Upbit account snapshot persistence in a dedicated crypto exchange namespace
- [x] Snapshot timestamp, age calculation, SHA-256 fingerprint, and reconciliation status
- [x] Database-level update/delete blocking for exchange snapshots
- [x] Tests for explicit opt-in, fail-closed behavior, redaction, persistence, and namespace isolation
- [x] GitHub Actions regression tests for all previously merged components

### In progress

- [ ] Confirm the new snapshot feature-branch regression suite in GitHub Actions
- [ ] Perform a supervised least-privilege read-only account probe with a real API key
- [ ] Validate Upbit public market data during sustained supervised PAPER operation
- [ ] Complete remaining compatibility cleanup for legacy root-level crypto imports

### Not started

#### Crypto

- [ ] Compare immutable exchange snapshots with PAPER observations without replacing PAPER state
- [ ] Exchange order-ID reconciliation after timeout
- [ ] `/ai_upbit_go -> /confirm -> /go` live approval flow
- [ ] Authenticated order submission, disabled until readiness and supervised PAPER gates pass

#### US stocks

- [ ] Select and implement a read-only US-stock market-data adapter
- [ ] Select a supported broker and build PAPER adapter
- [ ] US momentum/gap scanner and liquidity filters
- [ ] Separate USD cash, positions, orders, database namespace, approval flow, and runtime risk controls
- [ ] US-market-hours and holiday calendar handling
- [ ] US-stock-specific backtesting and paper-readiness gate

#### Shared intelligence

- [ ] News/sentiment input
- [ ] Chart-pattern features
- [ ] Market-regime detection
- [ ] EV and volatility-based sizing
- [ ] Model training and inference pipeline
- [ ] Deployment and operational monitoring

## Current behavior

1. The execution path remains `run.py -> telegram.py -> main.py -> TradingApplication`.
2. Crypto and US-stock baselines and state namespaces remain independent.
3. The active broker remains PAPER only unless the explicit LIVE guards are satisfied.
4. `AIPRO_MARKET_DATA_PROVIDER=DEMO` remains the safe offline default.
5. Upbit public market data remains separate from authenticated account inspection.
6. Authenticated account inspection is not wired into strategy decisions, PAPER balances, or order submission.
7. The supervised verification command requires `AIPRO_UPBIT_READONLY_VERIFY=YES`.
8. Setting `AIPRO_UPBIT_SNAPSHOT_DB` appends the observation to `exchange_account_snapshots`.
9. Exchange snapshot rows are append-only; database triggers reject updates and deletes.
10. Stored exchange values never replace PAPER cash, positions, orders, baselines, or strategy inputs.
11. Verification console output remains redacted even when the full local snapshot is persisted.
12. Order creation, cancellation, deposit, withdrawal, and mutation endpoints remain absent or blocked.
13. PAPER state remains the source of truth for simulated trading.

## Current gaps and risks

1. The authenticated client, verification command, and snapshot store have deterministic tests but have not yet been exercised with a real least-privilege Upbit API key.
2. A real API key must be IP-restricted and limited to account/order-view permissions; order and withdrawal permissions must remain disabled.
3. Full local snapshots contain sensitive financial values and exchange order identifiers; the database file needs restrictive filesystem permissions and backup controls.
4. Snapshot reconciliation is initially `UNCOMPARED`; PAPER comparison rules are not yet implemented.
5. Timeout reconciliation and immutable exchange-order identity rules remain unimplemented.
6. Upbit candle intervals with no trades may be absent; sparse markets can fail validation.
7. Backtests still use fixed slippage and do not model order-book depth or partial fills.
8. Exchange timestamp tolerance still requires sustained PAPER observation.
9. Archived evidence has no signed export and deletion policy.
10. US-stock broker, data, calendar, FX, tax, and fractional-share behavior remain unimplemented.
11. Legacy baseline keys remain for rollback compatibility and need a retirement version before removal.

## Immediate priority

### P0 — Confirm snapshot CI and run supervised verification

- Require all feature-branch tests to pass.
- Use an IP-restricted API key with only account-view and order-view permissions.
- Keep order, withdrawal, and deposit-management permissions disabled.
- Persist one supervised snapshot to a locally protected database.
- Record only the redacted console report outside the machine.

### P1 — Read-only snapshot comparison

- Define comparison-only rules against PAPER observations.
- Never mutate PAPER cash, positions, orders, or baseline from exchange data.
- Produce `MATCH`, `MISMATCH`, or `STALE` as new immutable reconciliation evidence rather than editing prior snapshots.

### P2 — Exchange order reconciliation design

- Define timeout lookup using exchange UUID and client identifier.
- Prevent duplicate submission after ambiguous network outcomes.
- Keep submission code absent until read-only inspection and supervised PAPER gates pass.

### P3 — Supervised crypto PAPER validation

- Run validated historical datasets through the readiness gate.
- Record dataset fingerprint, strategy/config version, and observation period.
- Require stable restart, HALTED, provider-health, and source-timestamp behavior.

## Completion policy

A task is complete only when implementation, tests, documentation, limitations, roadmap status, and next priority are recorded.

## Next action

Confirm feature-branch CI, perform one supervised read-only snapshot capture with a least-privilege key, then implement comparison-only reconciliation evidence without connecting exchange values to PAPER balances or strategy decisions.
