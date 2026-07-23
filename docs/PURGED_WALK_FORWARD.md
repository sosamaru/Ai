# Purged Walk-Forward Validation

This component creates deterministic PAPER-only validation folds for time-ordered financial observations.

## Leakage controls

- Training samples whose label windows overlap a test label window are purged.
- A configurable embargo records observations immediately after each test window.
- Crypto and US-stock observations cannot be mixed in one splitter.
- Duplicate indices, invalid label windows, invalid budgets, and empty fold plans fail closed.
- Expanding and bounded rolling training windows are supported.
- Every fold receives a SHA-256 evidence fingerprint.

## Safety boundary

The splitter does not load market data, train models, select production models, submit orders, or grant LIVE authority. Passing these folds is research evidence only. Model promotion still requires calibration, cost-aware expected value, untouched holdouts, portfolio risk checks, reconciliation, authorization, HALTED checks, and kill-switch readiness.
