# Purged PAPER Training Runner

## Purpose

`aipro.research.purged_training_runner` provides the first concrete, dependency-free PAPER model-training path in AiPro. It trains a deterministic logistic classifier independently inside each purged walk-forward fold and converts held-out fold results into the existing classical candidate-evaluation contract.

## Validation flow

1. Validate binary labels, finite features, unique indices, fixed feature width, and one isolated asset domain.
2. Build chronological folds with `PurgedWalkForwardSplitter`.
3. Purge training rows whose label windows overlap the test label window.
4. Record post-test embargo indices.
5. Fit feature scaling using training rows only.
6. Train a bounded deterministic logistic classifier using training rows only.
7. Score untouched test rows using balanced accuracy, Brier score, cost-aware expected value, turnover, and sample count.
8. Pass fold evidence into `evaluate_candidate` for the existing fail-closed candidate gate.
9. Produce deterministic fold, model, evaluation, and report SHA-256 fingerprints.

## Domain isolation

Crypto and U.S.-stock rows cannot be mixed. The candidate domain is inherited from the validated dataset and remains explicit in every evaluation and report.

## Safety boundary

The runner:

- does not fetch market data;
- does not persist or serve model binaries;
- does not mutate a champion registry;
- does not contact a broker;
- does not submit, cancel, replace, or retry orders;
- does not enable PAPER or LIVE execution;
- cannot bypass authorization, HALTED, kill-switch, reconciliation, freshness, portfolio-risk, or readiness gates.

A positive held-out result is research evidence only. It is not proof of future profitability or live readiness.

## Current limitation

This first runner supports a deterministic binary logistic baseline only. Optional boosting and sequence-model backends still require separate bounded training adapters that reuse the same purged fold and evidence contracts without importing optional dependencies during normal application startup.
