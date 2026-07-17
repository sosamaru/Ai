# Security Policy

## Scope

AiPro handles trading credentials and may eventually control financial orders. Security defects must therefore fail closed: the system should stop trading rather than guess, retry indefinitely, or continue with uncertain state.

## Non-negotiable rules

- Never commit API keys, Telegram tokens, chat IDs, account data, or `.env` files.
- Use exchange keys with the minimum possible permissions and no withdrawal permission.
- Keep LIVE trading disabled by default.
- Treat logs, database backups, screenshots, and CI artifacts as potentially sensitive.
- Rotate any credential immediately if it appears in a commit, log, message, or screenshot.
- Do not enable order endpoints before reconciliation, idempotency, retry limits, and kill-switch tests are complete.

## LIVE activation gates

All of the following must be true:

1. `AIPRO_MODE=LIVE`
2. `ENABLE_LIVE_TRADING=1`
3. `AIPRO_LIVE_CONFIRM=YES`
4. `MAX_ORDER_KRW` is positive and conservatively capped
5. The 30-day PAPER deployment gate in `PROJECT_ROADMAP.md` has passed
6. Balance, order, and fill reconciliation is healthy
7. The owner explicitly approves a small-capital pilot

Any missing or malformed condition must prevent order submission.

## Incident response

1. Set `ENABLE_LIVE_TRADING=0` and stop the process.
2. Revoke or rotate exchange and Telegram credentials.
3. Preserve logs and database snapshots without publishing them.
4. Reconcile exchange balances, open orders, and fills manually.
5. Document root cause, affected interval, and remediation.
6. Add a regression test before restoring PAPER operation.
7. Repeat release gates before considering LIVE operation again.

## Reporting

Document security findings privately. Do not include real credentials, complete account identifiers, or exploitable production details in public issues.
