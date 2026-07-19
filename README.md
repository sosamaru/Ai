# AiPro

Safe-by-default multi-asset automated-trading foundation.

## Execution flow

`run.py -> telegram.py -> main.py -> TradingApplication`

The execution flow remains unchanged while asset-specific code is separated behind domain packages.

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

## Run

Without a Telegram token, AiPro executes one console cycle:

```bash
python run.py
```

To enable Telegram polling, set both variables:

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

```bash
python -m pytest -q
```

## Operational validation required

The following are elapsed-time or owner-controlled validation tasks, not missing implementation:

1. Configure a dedicated SMTP or transactional-email account and verify OTP delivery.
2. Enroll the TOTP secret in an authenticator application and store recovery material offline.
3. Add actual Alpaca PAPER credentials and collect at least 30 calendar days of qualifying evidence.
4. Add an IP-restricted Upbit key and run supervised inspection/test-order checks with real order creation disabled.
5. Review all evidence and issue a separate live-readiness decision.

## Safety boundary

This repository does not create real-money orders. Email OTP, TOTP, confidence scores, recent profits, or expert opinions cannot bypass failed risk, freshness, reconciliation, readiness, or kill-switch gates. Real order submission must remain absent until every mandatory gate in `PROJECT_ROADMAP.md` passes and a separate live-readiness review explicitly approves it.
