# Operational adapters

This milestone completes the source-code components required before supervised credentials and elapsed PAPER evidence can be supplied.

## Authentication

- SMTP email OTP sender using Python's standard SMTP and email packages
- RFC 6238-compatible TOTP verification
- expiring two-factor authorization lease
- append-only authorization audit evidence

Secrets must be injected through environment variables or a protected secret manager and must never be committed.

## Alpaca PAPER

The adapter accepts only `https://paper-api.alpaca.markets` and rejects the live domain. It supports PAPER account inspection, positions, PAPER order submission, client-order lookup, duplicate client-order-ID rejection, and deterministic evidence.

PAPER execution is not evidence of LIVE readiness until the configured minimum 30-day window and all readiness metrics pass.

## Upbit preflight

The Upbit adapter generates an HS512 JWT with a SHA-512 request hash and calls only `/v1/orders/test`. This endpoint validates an order without creating it. Availability depends on the Upbit regional API and account permissions.

## Final execution gate

A future real-order adapter must fail closed unless every configured authorization, PAPER, reconciliation, freshness, provider-health, risk, uniqueness, preflight, and kill-switch condition passes simultaneously.

No real-order endpoint is included in this milestone.
