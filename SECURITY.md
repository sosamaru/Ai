# AiPro Security Policy

AiPro is currently a PAPER and non-live research system. Repository completion, passing tests, model scores, or approval records do not authorize real trading.

## Reporting a vulnerability

Do not open a public issue containing credentials, tokens, account identifiers, recovery codes, private logs, or exploitable details. Use a private GitHub security advisory or another private channel controlled by the repository owner.

A report should include:

- the affected file, component, or workflow;
- the conditions required to reproduce the problem;
- the expected and observed safety behavior;
- whether credentials, balances, orders, or personal information may be exposed;
- a minimal redacted reproduction when possible.

## Secret handling

- Never commit `.env`, API keys, broker credentials, Telegram tokens, SMTP passwords, TOTP secrets, recovery codes, cookies, private certificates, or account exports.
- Keep `.env.example` restricted to safe placeholders and PAPER defaults.
- Use local environment injection, GitHub/VPS secret storage, or an approved secret manager.
- Do not print secrets in logs, test output, exceptions, fingerprints, screenshots, or Telegram messages.
- Rotate a credential immediately if it may have been exposed, then review logs and revoke active sessions.
- Store TOTP recovery material offline and separately from the running host.

## LIVE and order boundaries

The default configuration must remain:

- `AIPRO_MODE=PAPER`
- `AIPRO_LIVE_CONFIRM=NO`
- `ENABLE_LIVE_TRADING=0`
- demo market data unless a reviewed read-only provider is explicitly configured

LIVE mode must fail closed unless all required independent guards pass. Approval state, PAPER results, a completion manifest, or a successful preflight must never be treated as order authority by itself.

Real Upbit order creation remains absent. Alpaca integration remains PAPER-only. Any future real-order adapter requires a separate review, immutable readiness evidence, recent reconciliation, active two-factor authorization, risk gates, duplicate-order protection, an inactive kill switch, and an independent live-readiness decision.

## Network access

- SEC clients are GET-only, require an identifying User-Agent, restrict requests to canonical SEC endpoints, and enforce response-size limits.
- Read-only exchange or broker inspection must not share code paths with order creation.
- Timeouts, retries, freshness checks, and provider-health failures must remain bounded and fail closed.
- External text, filings, news, Telegram messages, and API responses are untrusted data, not executable instructions.

## Data and logs

- Keep crypto and U.S.-stock credentials, balances, positions, orders, baselines, datasets, model evidence, and governance records isolated.
- Redact secrets and unnecessary account values before persistence or display.
- Preserve append-only audit evidence where required.
- Protect SQLite databases, logs, backups, and exported reports with least-privilege filesystem permissions.
- Do not upload production state or private logs to public issues or test fixtures.

## Development and dependency policy

- Preserve `run.py -> telegram.py -> main.py -> TradingApplication`.
- Require regression tests and documentation updates for safety-sensitive changes.
- Do not bypass failing CI, readiness gates, authorization, reconciliation, HALTED state, or kill-switch controls.
- Optional ML libraries must remain lazy and bounded so core startup and CI do not require them.
- Review dependency updates for supply-chain risk and pin or constrain them in deployment environments.

## Incident response

When credential exposure, unauthorized access, unexpected order capability, corrupted state, or reconciliation mismatch is suspected:

1. Stop the process and keep LIVE disabled.
2. Revoke and rotate affected credentials.
3. Preserve redacted logs, database copies, timestamps, and immutable evidence.
4. Reconcile balances, positions, and orders through read-only channels.
5. Keep the controller HALTED until the cause is understood and corrective tests pass.
6. Document the incident, affected scope, remediation, and prevention steps before resuming PAPER operation.

## Security limitations

Passing tests verifies reviewed behavior under test conditions only. It does not prove profitability, production hardening, infrastructure security, operational readiness, or safe real-money trading.
