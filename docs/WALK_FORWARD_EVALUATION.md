# Walk-forward evaluation

This module evaluates timestamped `paper-feature-vector-v1` evidence without connecting research output to broker execution.

## Guarantees

- Rows are sorted chronologically.
- Duplicate timestamps and duplicate feature fingerprints are rejected.
- Mixed schemas and inconsistent feature widths are rejected.
- Every test window starts after the training window.
- An embargo gap can be enforced between train and test windows.
- Metrics are calculated only from held-out test rows.
- Reports preserve deterministic SHA-256 evidence lineage.

## Baseline model

The initial model is deterministic ridge regression implemented with the Python standard library. It is a transparent research baseline, not a profitability claim. Future models must be compared against it using the same chronological folds.

## Limitations

- Labels must already be generated without future-data leakage.
- The module does not account for fees, slippage, fills, liquidity limits, or portfolio interactions.
- Directional accuracy, MAE, and RMSE do not authorize trading.
- A successful report cannot bypass PAPER-readiness, reconciliation, risk, authorization, or kill-switch gates.
- Crypto and US-stock datasets and reports must remain separate.
