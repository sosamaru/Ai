# AiPro

Safe-by-default multi-asset automated-trading foundation.

## Survival-first runtime hardening — 2026-09-21

The canonical PAPER path now rejects corrupt account recovery, unreconciled state,
invalid numerical inputs and uncalibrated model entries. Risk is rechecked after
exits; model acceptance includes statistical rejection. Prospective US file-fed
frames are archived before execution for shared-pipeline replay.

Local verification: **619 regression tests and 158 integration tests passed**.
This is software evidence, not profitability. Actual qualifying PAPER evidence
remains **0/30 days supplied**, and LIVE remains blocked. Legacy v1/v2 model
artifacts require retraining to calibrated v3 before serving. Ensemble trading
and cohort promotion remain blocked where their mandatory evidence is missing.

See [the audit and P0–P3 plan](docs/SURVIVAL_FIRST_AUDIT_20260920.md) and
[the current PAPER/Shadow runbook](docs/SURVIVAL_RUNTIME_20260921.md).

## AI runtime audit and model pipeline — 2026-09-14

The latest PR #75 work now includes a bounded CPU logistic-model training,
final-holdout evaluation, numeric JSON export, and explicitly pinned inference
path for the US short sleeve. Purging now checks outcome availability at the
prediction instant, prior embargo rows are excluded from later training, and
model failures cannot roll back required portfolio exits.

```bash
python -m aipro model-train data/us_frames.jsonl --symbol AAPL --experiment-id aapl-v3-001 --output-dir data/models/aapl
python -m aipro model-inspect data/models/aapl/model.json
```

These commands require the documented historical US-frame input and at least
600 non-overlapping labeled samples. No validated real-market model is supplied.
Runtime model selection requires both `AIPRO_US_MODEL_PATH` and
`AIPRO_US_MODEL_SHA256`; defaults remain the untrained rule baseline.
Synthetic artifacts are restricted to explicit synthetic replay. This does not
wire a broker or establish profitability, elapsed PAPER evidence, or LIVE readiness.

See [the Korean audit, model design, commands and remaining work](docs/AI_RUNTIME_AUDIT_20260914.md).
Historical construction percentages cover their named scopes; the wider service
and Issue #48 technology requirements remain incomplete.

## US-stock dual portfolio — 2026-09-12

An executable **local PAPER simulator** now supports the owner's fixed funding plan:
KRW 200,000 intraday + KRW 800,000 long-term, no further external contributions,
isolated cash and realized-profit reinvestment, persistent risk stops, transaction
costs, settlement delays, and chronological replay. The 2% short-sleeve daily
target is a profit-stop condition, not a profitability promise.

```bash
python -m aipro portfolio-demo
```

The demo uses invented data. Select `AIPRO_RUNTIME=US_DUAL` for the canonical
runtime and use `config/us_dual_paper.env.example` for file-fed continuous PAPER
execution. Without this selector the existing crypto runtime remains the default.
This profile does not contact a brokerage or place actual/PAPER API orders.
The default strategies are untrained rules; data-feed integration, fitted-model
validation, corporate-action accounting, and real broker validation remain pending.

See [the Korean execution and limitations guide](docs/US_DUAL_PORTFOLIO.md).

## Execution flow

`run.py -> telegram.py -> main.py -> TradingApplication`

The execution flow remains unchanged while asset-specific code is separated behind domain packages. `run.py` loads an optional local `.env` file before launch without overwriting environment variables already injected by a shell, CI system, VPS secret manager, or service supervisor.

## Runtime compatibility

- Supported core runtime: Python 3.11, 3.12, and 3.13
- Core execution dependencies: Python standard library only
- Test dependency: pytest
- CI checks: environment diagnosis, source/test compilation, canonical PAPER entrypoint execution, explicit integration tests, and the complete test suite with warnings treated as errors on every supported Python version

## Domain layout

```text
aipro/
├── core/          # asset-neutral contracts and safety boundaries
├── crypto/        # crypto configuration, adapters, and strategies
├── us_stocks/     # US-stock configuration, adapters, and strategies
└── intelligence/  # broker-neutral news and sentiment inputs
```

Crypto and US-stock capital, broker state, credentials, risk limits, approval state, order identifiers, strategies, and daily baselines must remain isolated.

## Current completion state

- V1 foundation: complete.
- V2 approved non-live integration scope: complete.
- Real-money trading approval: not granted.
- Crypto runtime: PAPER by default; authenticated Upbit inspection and `/v1/orders/test` preflight are available, but real order creation is absent.
- US-stock runtime: Alpaca PAPER-only account, order, order-list, and reconciliation lookup are available; live Alpaca domains are rejected.
- Operational validation: dedicated SMTP/TOTP setup, supervised Upbit checks, and at least 30 calendar days of qualifying Alpaca PAPER evidence are still required.

Legacy root modules remain in use where needed to preserve restart compatibility and are migrated only when the existing execution path remains stable.

## Included

- PAPER mode by default and explicit LIVE environment guards
- Persistent PAPER cash, positions, average prices, order IDs, and restart recovery
- Persistent KST daily baselines and daily-loss HALT latch
- Historical replay, dataset validation, fingerprints, and readiness reports
- Upbit public quotation adapter with freshness and provider-health gates
- Isolated authenticated Upbit account/order inspection and immutable evidence
- Upbit `/v1/orders/test` preflight with hard separation from `/v1/orders`
- Duplicate-order blocking and `MATCH`/`MISMATCH`/`STALE` reconciliation evidence
- Restart-safe `/ai_upbit_go -> /confirm -> /go` approval-intent flow
- Email OTP plus RFC 6238 TOTP temporary authorization lease
- Atomic authorization persistence, lockout, revocation, and append-only audit evidence
- Alpaca PAPER-only adapter and minimum 30-day readiness policy
- Session, order-count, expectancy, drawdown, daily-loss, stale-data, duplicate-order, and reconciliation gates
- Finnhub news and Alpha Vantage sentiment adapters
- Deduplication, symbol relevance, sentiment fusion, event classification, caching, rate limiting, retry, and circuit breaking
- Freshness-gated intelligence snapshots with deterministic SHA-256 fingerprints
- Authenticated Telegram commands, SQLite state/evidence storage, logging, regression tests, and GitHub Actions
- Unified local/Windows/VPS execution commands with actionable diagnostics
- Manually runnable GitHub workflow for doctor, compile, smoke, integration, full tests, or the complete validation chain

## Quick execution and recovery

The unified command interface makes every execution stage return a clear success/failure code and identifies the failed stage.

Windows Command Prompt:

```bat
aipro.cmd doctor --require-pytest
aipro.cmd smoke
aipro.cmd integration
aipro.cmd all
aipro.cmd run
```

Windows PowerShell:

```powershell
.\aipro.ps1 doctor --require-pytest
.\aipro.ps1 smoke
.\aipro.ps1 integration
.\aipro.ps1 all
.\aipro.ps1 run
```

Cross-platform:

```bash
python -m aipro doctor --require-pytest
python -m aipro compile
python -m aipro smoke
python -m aipro integration
python -m aipro test
python -m aipro all
python -m aipro run
```

When a machine reports execution unavailable, run in this order:

```text
doctor -> compile -> smoke -> integration -> test -> run
```

`doctor` checks the Python version, entrypoint files, imports, `.env`/environment validation, writable DB/log paths, and pytest availability. `smoke` uses temporary storage, DEMO market data, no Telegram token, and PAPER mode, so it separates core-runtime failures from external API, credential, firewall, DNS, proxy, or provider failures.

Detailed commands and error corrections are in `docs/EXECUTION_RUNBOOK.md`.

## Run

Create a local configuration only when needed:

```bash
cp .env.example .env
```

A local `.env` file is optional. Existing process environment variables always take precedence, so CI/VPS secret injection is not overwritten.

Without a Telegram token, AiPro executes one safe PAPER console cycle:

```bash
python run.py
```

The equivalent unified command is:

```bash
python -m aipro run
```

To enable Telegram polling, set both variables in the process environment or local `.env` file:

```bash
AIPRO_TELEGRAM_BOT_TOKEN=<bot-token>
AIPRO_TELEGRAM_ALLOWED_CHAT_IDS=<numeric-chat-id>
python run.py
```

Multiple chat IDs may be comma-separated. Never commit tokens or credentials.

Supported commands depend on the configured runtime and include status inspection, a supervised PAPER cycle, HALT recovery, and the guarded Upbit approval flow. Unauthorized chat IDs cannot execute commands.

## Supervised Upbit read-only verification

Use an IP-restricted Upbit API key with only the minimum inspection permissions required. Withdrawal and deposit-management permissions must remain disabled.

```bash
AIPRO_UPBIT_READONLY_VERIFY=YES
AIPRO_UPBIT_ACCESS_KEY=<access-key>
AIPRO_UPBIT_SECRET_KEY=<secret-key>
AIPRO_UPBIT_SNAPSHOT_DB=data/upbit_readonly_snapshots.sqlite3
python -m aipro.crypto.verify_readonly
```

When configured, the snapshot database appends immutable exchange observations. It does not overwrite PAPER balances, positions, orders, baselines, strategy inputs, or authorization state. Console output remains redacted.

## Test

Install pytest once in the selected supported Python environment:

```bash
python -m pip install --upgrade "pytest>=8,<10"
```

Then run either the unified complete verification:

```bash
python -m aipro all
```

or the direct full regression command:

```bash
python -m pytest -q -W error
```

The GitHub Actions workflow diagnoses the environment, compiles the repository, runs `python run.py` in PAPER mode, runs the explicit integration group, and executes the complete regression suite on Python 3.11, 3.12, and 3.13. The separate manual workflow exposes the same targets through the Actions tab once present on the default branch.

## Operational validation required

The following are elapsed-time or owner-controlled validation tasks, not missing implementation:

1. Configure a dedicated SMTP or transactional-email account and verify OTP delivery.
2. Enroll the TOTP secret in an authenticator application and store recovery material offline.
3. Add actual Alpaca PAPER credentials and collect at least 30 calendar days of qualifying evidence.
4. Add an IP-restricted Upbit key and run supervised inspection/test-order checks with real order creation disabled.
5. Review all evidence and issue a separate live-readiness decision.

## Safety boundary

This repository does not create real-money orders. Email OTP, TOTP, confidence scores, recent profits, or expert opinions cannot bypass failed risk, freshness, reconciliation, readiness, or kill-switch gates. Real order submission must remain absent until every mandatory gate in `PROJECT_ROADMAP.md` passes and a separate live-readiness review explicitly approves it.
