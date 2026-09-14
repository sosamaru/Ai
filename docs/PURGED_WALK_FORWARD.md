# Purged Walk-Forward Validation

This component creates deterministic PAPER-only validation folds for time-ordered financial observations.

## Leakage controls

- Training samples whose label windows overlap a test label window are purged.
- Training outcomes must also end strictly before the first test prediction index,
  even if that test observation's label window starts later.
- A configurable embargo records observations immediately after each test window
  and excludes them from subsequent training folds in the same validation plan.
- Test windows cannot overlap (`step_size >= test_size`), so the same test sample
  cannot be counted repeatedly as independent evidence.
- Empty post-purge training folds fail closed. Logistic fitting also requires both
  target classes within each training fold.
- Crypto and US-stock observations cannot be mixed in one splitter.
- Duplicate indices, invalid label windows, invalid budgets, and empty fold plans fail closed.
- Expanding and bounded rolling training windows are supported.
- Every fold receives a SHA-256 evidence fingerprint.

These semantics were corrected on 2026-09-14. Earlier fingerprints and model
scores must not be presented as results of the corrected splitter. Re-run affected
research before promotion. This forward-only splitter is not a CPCV implementation.

## Safety boundary

The splitter does not load market data, train models, select production models, submit orders, or grant LIVE authority. Passing these folds is research evidence only. Model promotion still requires calibration, cost-aware expected value, untouched holdouts, portfolio risk checks, reconciliation, authorization, HALTED checks, and kill-switch readiness.
