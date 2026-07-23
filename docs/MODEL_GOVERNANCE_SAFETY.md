# PAPER Model Governance Safety

This layer is research-only and does not create, modify, approve, or route orders.

## Drift detection

- Reference and current windows are validated separately.
- Mixed schemas and inconsistent feature widths are rejected.
- Insufficient windows fail closed.
- Drift indicates distribution change, not a trading signal.

## Feature ablation

- Every ablated feature set is evaluated through the same chronological walk-forward process.
- Held-out metrics remain out-of-sample.
- Better ablation results do not prove profitability or live readiness.

## Model registry

- Only eligible walk-forward reports may be registered.
- Model IDs are immutable and duplicate IDs are rejected.
- Crypto and US-stock records use separate explicit asset domains.
- Registry status is limited to `paper_candidate` and cannot bypass authorization, reconciliation, risk, or readiness gates.
- Fingerprints provide evidence lineage; they are not signatures or guarantees.
