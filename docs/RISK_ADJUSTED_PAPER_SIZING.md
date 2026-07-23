# Risk-adjusted PAPER sizing

This component converts a validated probabilistic forecast into a broker-neutral PAPER sizing decision. It does not submit, modify, cancel, or retry orders.

## Inputs

- domain (`crypto` or `us_stocks` only)
- account equity and unit price
- stop distance and forecast volatility
- win probability, expected gain, expected loss, and estimated transaction cost
- bounded uncertainty score
- conservative policy caps

## Decision process

1. Reject malformed, non-finite, zero-risk, or cross-domain inputs.
2. Calculate gross expected value and subtract estimated transaction cost.
3. Calculate a non-negative, capped fractional-Kelly signal.
4. Abstain when net expected value or Kelly edge is non-positive.
5. Calculate stop-risk notional from a fixed account risk budget.
6. Reduce size for excess volatility and forecast uncertainty.
7. Apply a hard maximum-position cap.
8. Produce a deterministic SHA-256 fingerprint for audit and lineage.

## Safety boundaries

- Outputs are PAPER research suggestions, never broker instructions.
- Crypto and US-stock decisions cannot share a domain identifier.
- No positive expected-value estimate bypasses portfolio, readiness, reconciliation, freshness, authorization, or kill-switch gates.
- Kelly sizing is deliberately capped and is not a profitability guarantee.
- Transaction-cost estimates must later be supplied by the execution-cost simulator rather than assumed away.
