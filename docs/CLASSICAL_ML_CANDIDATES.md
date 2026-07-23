# Classical ML Candidate Governance

This module defines a PAPER-only contract for classical machine-learning candidates.

## Candidate families

The built-in registry names logistic regression, ElasticNet, random forest, extra trees, and gradient boosting. The contract does not require optional third-party libraries and does not claim that every family is installed or trained.

## Evaluation gate

Candidates are evaluated from fold-level evidence. Acceptance requires sufficient folds and samples, balanced accuracy above the configured floor, Brier score below the ceiling, positive cost-aware expected value, and stable performance across folds.

Rejected candidates remain research artifacts and cannot become a champion. Ranking excludes rejected candidates and refuses to combine crypto and US-stock domains.

## Safety boundary

This code does not load market data, fit production models, contact a broker, submit orders, or promote a model to LIVE use. Candidate acceptance is only one research signal and cannot bypass purged validation, locked holdouts, risk limits, reconciliation, authorization, HALTED state, or kill-switch controls.

Every evaluation receives a deterministic SHA-256 fingerprint for audit and reproducibility checks.
