# AiPro Project Roadmap

Updated: 2026-07-19

## Project goal

Build a safe, maintainable multi-asset automated-trading foundation while preserving:

`run.py -> telegram.py -> main.py -> TradingApplication`

Crypto and US-stock capital, credentials, broker state, risk limits, order IDs, approval state, and daily baselines remain isolated.

## V1 foundation status

Overall completion: **100%**

The V1 architecture, PAPER persistence, replay, reconciliation, approval intent, news intelligence, resilience, event classification, and PAPER feature snapshot scope is complete.

## V2 implementation status

Current code milestone: **100% complete**

### Completed

- [x] Email OTP first-factor state machine
- [x] Secret-safe SMTP OTP sender adapter
- [x] RFC 6238-compatible TOTP second-factor verifier
- [x] Salted OTP digest, expiry, failed-attempt lockout, and revocation
- [x] Temporary LIVE authorization lease with forced reauthentication
- [x] Append-only authorization audit evidence
- [x] Alpaca PAPER-only domain and credential boundary
- [x] Alpaca PAPER account, position, order, lookup, duplicate-ID, and evidence adapter
- [x] Minimum 30-day Alpaca PAPER readiness policy
- [x] Upbit authenticated non-executing test-order/preflight adapter
- [x] HS512 JWT and SHA-512 request hash generation for Upbit preflight
- [x] Fail-closed combined LIVE execution gate
- [x] Regression tests and documentation

## Mandatory execution gate

Every future real order must satisfy all conditions simultaneously:

1. Explicit LIVE environment guards.
2. Active email OTP plus TOTP authorization lease.
3. Recent PAPER validation PASS.
4. Required training window PASS for the relevant asset domain.
5. Recent reconciliation `MATCH` evidence.
6. Fresh market and intelligence data.
7. Healthy required providers.
8. Daily-loss, drawdown, exposure, liquidity, and position-size limits.
9. Unique client order identifier.
10. Accepted exchange preflight/test result when supported.
11. Global kill switch inactive.

No OTP, Telegram command, expert opinion, confidence score, or recent profit may bypass a failed gate.

## Operational work that cannot be completed by source code alone

The software implementation is complete for the current milestone. The following require the owner's real accounts, credentials, elapsed time, and supervised evidence:

- Configure the owner's SMTP account and destination email.
- Enroll a TOTP secret in the owner's authenticator and store the secret outside Git.
- Add Alpaca PAPER credentials and run at least 30 calendar days.
- Accumulate the required completed sessions, orders, fills, daily reports, and reconciliation evidence.
- Add an IP-restricted Upbit key and run test-order/preflight plus supervised market-data collection.
- Review the resulting drawdown, expectancy, stale-data, duplicate-order, and unreconciled-order metrics.
- Conduct a separate live-readiness review before any real-order endpoint is added.

## Investment-intelligence policy

- Expert opinions are timestamped evidence, never direct order commands.
- Claims must be mapped to symbols, events, horizon, and measurable outcomes.
- Source weights must be based on out-of-sample historical accuracy and decay when performance deteriorates.
- News, filings, macro, chart, volume, volatility, liquidity, regime, and portfolio risk are combined.
- The target is risk-adjusted expected value and controlled drawdown, not maximum aggression.
- Disagreement, stale data, uncertainty, and drift reduce or block position size.
- No profitability guarantee is permitted.

## Completion meaning

Code completion does not mean profitable trading or production readiness. Actual LIVE eligibility remains false until the required 30-day PAPER evidence, Upbit supervised evidence, real credential configuration, and independent live-readiness review are completed.

## Next action

Configure secrets outside Git and begin the 30-day Alpaca PAPER evidence run. Keep real order submission absent during the evidence period.
