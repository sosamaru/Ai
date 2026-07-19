# AiPro final integration runbook

## Scope

The approved development scope is complete for two-factor authorization, Alpaca PAPER operation, Upbit test-order validation, and append-only evidence collection. Real-money order creation remains intentionally absent.

## Secret configuration

Store all values outside Git:

- `AIPRO_SMTP_HOST`
- `AIPRO_SMTP_PORT`
- `AIPRO_SMTP_USERNAME`
- `AIPRO_SMTP_PASSWORD`
- `AIPRO_SMTP_SENDER`
- `AIPRO_TOTP_SECRET`
- `APCA_PAPER_API_KEY_ID`
- `APCA_PAPER_API_SECRET_KEY`
- `UPBIT_ACCESS_KEY`
- `UPBIT_SECRET_KEY`

Use a dedicated SMTP account, an authenticator-app TOTP secret, Alpaca PAPER-only credentials, and an IP-restricted Upbit key. Never commit `.env`, recovery codes, API keys, or email passwords.

## Authorization flow

1. Request email OTP.
2. Verify the six-digit OTP before expiry.
3. Verify TOTP from the enrolled authenticator.
4. Persist the temporary authorization lease atomically.
5. Append an audit event without storing OTP plaintext or TOTP secrets.
6. Revoke on `/stop`, expiry, excessive failures, HALTED state, provider failure, or risk-gate failure.

Authorization never bypasses PAPER validation, reconciliation, freshness, exposure, drawdown, daily-loss, or duplicate-order checks.

## Alpaca PAPER run

The client rejects every base URL except `https://paper-api.alpaca.markets`.

Collect account and order evidence into the append-only store at least daily and after significant fills or restarts. Continue for at least 30 calendar days. A passing run requires the configured minimum sessions and orders, positive out-of-sample expectancy, controlled drawdown and daily loss, fresh data, zero duplicate client order IDs, and zero unresolved reconciliation failures.

## Upbit supervised validation

The Upbit adapter contains only `POST /v1/orders/test`. It does not contain the real `POST /v1/orders` endpoint. Run test-order checks with a small valid payload and record the response as evidence. Do not enable withdrawal permissions.

## Stop conditions

Immediately revoke authorization and stop processing when any of these occurs:

- operator `/stop`
- lease expiry
- HALTED latch
- daily-loss or drawdown breach
- stale market or intelligence data
- unhealthy mandatory provider
- duplicate order identifier
- unresolved reconciliation mismatch
- unexpected broker domain or endpoint

## What remains operational, not developmental

Actual SMTP delivery verification, TOTP enrollment, the real 30-day elapsed Alpaca PAPER run, supervised Upbit preflight checks, and an independent live-readiness review require external credentials and elapsed real-world operation. They cannot be honestly marked complete by code alone.
