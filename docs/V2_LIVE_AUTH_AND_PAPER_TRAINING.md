# AiPro V2 Live Authorization and PAPER Training

## Purpose

This milestone adds a safe authorization boundary and a measurable PAPER-training gate. It does not add authenticated order submission.

## Two-factor authorization

1. Operator requests authorization.
2. A six-digit one-time code is sent to the configured owner email.
3. The email code expires quickly and is stored only as a salted SHA-256 digest.
4. A separate second factor must be verified after the email code.
5. Success creates a temporary authorization lease.
6. `/stop`, HALTED, risk breach, restart-policy failure, or lease expiry revokes the lease.
7. Restart must not silently extend an expired lease.

The lease is intentionally time-limited. An authorization that remains active forever is unsafe if a phone, email account, Telegram account, API key, or server is compromised.

## Required runtime gates before any future order submission

A future order adapter must require all of the following at the same time:

- explicit LIVE configuration guards
- recent two-factor authorization lease
- recent supervised PAPER validation PASS
- recent reconciliation MATCH evidence
- fresh market and intelligence data
- provider health PASS
- daily-loss and maximum-drawdown limits
- unique client order identifier
- order preflight/test validation when supported
- global kill switch not active

No single OTP or Telegram command may bypass these gates.

## Alpaca PAPER training

Alpaca PAPER credentials and domain must remain separate from live credentials and domains. The default training window is at least 30 calendar days.

Training PASS requires:

- at least 30 calendar days
- at least 20 completed market sessions
- at least 50 completed orders
- positive expectancy per completed trade
- maximum drawdown within policy
- worst daily loss within policy
- zero duplicate-order events
- zero unreconciled-order events
- zero stale-data eligibility events

A high return does not override a safety failure.

## Intelligence direction

Expert commentary is evidence, not authority. The system should extract claims, timestamp them, map them to symbols and events, score source reliability using historical outcomes, and combine them with price, volume, volatility, liquidity, macro, filing, and news features.

The objective is risk-adjusted expected value, not maximum aggression. Confidence must reduce position size when evidence disagrees, data is stale, or regime uncertainty is high.

## Planned sequence

1. Email sender adapter and TOTP verifier.
2. Persisted authorization state and audit evidence.
3. Alpaca PAPER account/read/order adapter using PAPER-only credentials.
4. Thirty-day evidence collector and daily report.
5. Upbit authenticated test-order/preflight adapter where supported.
6. Supervised Upbit real-data collection without real order creation.
7. Strategy evaluation, drift checks, and independent live-readiness review.
8. Only after review: minimal order adapter behind every gate above.
