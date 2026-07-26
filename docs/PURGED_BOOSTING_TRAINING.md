# Purged optional boosting training

This construction stage connects the existing lazy XGBoost, LightGBM, and CatBoost factories to the existing purged walk-forward validation contract.

## Guarantees

- Backends are imported only after an explicit research call.
- Crypto and U.S.-stock rows cannot be mixed.
- Every fold is checked for label-window leakage.
- A new estimator is created for each fold.
- Test rows remain untouched until scoring.
- Balanced accuracy, Brier score, cost-aware expected value, turnover, and sample counts flow through the existing candidate evaluator.
- Backend parameters, fold identity, and held-out probabilities receive deterministic SHA-256 evidence fingerprints.
- Invalid backend names, seeds, probability shapes, probability ranges, and row domains fail closed.

## Resource boundary

The existing optional-backend registry limits estimator counts or iterations and forces single-thread deterministic execution. Unknown parameters are rejected. CatBoost file writing remains disabled by default.

## Non-authority

A successful report is PAPER research evidence only. It does not persist or serve a model, contact a broker, submit an order, change champion state, enable LIVE mode, or bypass readiness, risk, reconciliation, authorization, HALTED, or kill-switch gates.

Optional packages are not required for core startup or the normal CI suite. Tests use a deterministic fake estimator so dependency isolation remains verifiable.
