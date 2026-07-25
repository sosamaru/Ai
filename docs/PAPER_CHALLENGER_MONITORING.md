# PAPER Challenger Monitoring

AiPro evaluates champion and challenger health snapshots without automatically changing the champion registry.

## Inputs

Each snapshot is domain-specific and records candidate and evaluation fingerprints, aggregate score, drift score, Brier calibration score, cost-aware expected value, drawdown, and observation count.

## Recommendations

- `hold`: current evidence does not justify a governance change.
- `review_replacement`: a healthy challenger exceeds both score and expected-value margins.
- `review_rollback`: the champion is degraded and no decisive healthy challenger is available.
- `deactivate`: the champion has non-positive expected value or breaches the drawdown ceiling.
- `abstain`: evidence is insufficient for a reliable recommendation.

## Fail-closed rules

- Crypto and US-stock snapshots cannot be mixed.
- A candidate cannot challenge itself.
- Minimum observation counts are required.
- Drift, calibration, expected value, and drawdown gates apply independently.
- An unhealthy challenger cannot replace a champion.
- Every decision receives a deterministic SHA-256 fingerprint.

## Safety boundary

The monitor produces review evidence only. It cannot activate, replace, roll back, or deactivate a registry entry; train, load, persist, or serve a model; contact a broker; create an order; enable LIVE mode; bypass authorization, HALTED, reconciliation, portfolio-risk, or kill-switch gates. Registry changes remain explicit operator-governed append-only events.
