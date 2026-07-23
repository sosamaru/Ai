# PAPER sequence-model backends

This construction stage defines reviewed specifications for LSTM, GRU, and
Transformer-encoder research candidates. It does not train, save, promote, or
serve a model.

## Isolation rules

- `torch` and `tensorflow` are optional dependencies.
- Core application startup and CI do not import either package.
- Availability inspection uses module metadata only.
- Import occurs only after an explicit research request and successful spec
  validation.
- Crypto and US-stock candidates retain separate domain identities, datasets,
  baselines, validation evidence, and registries.

## Fail-closed limits

Specifications reject unknown backends, model families, parameters, duplicate
features, invalid attention geometry, excessive epochs, oversized networks, and
invalid optimization values. Defaults are deterministic and include a fixed
seed.

## Non-authority

A validated specification or installed backend is PAPER research evidence only.
It provides no market-data loading, training orchestration, artifact persistence,
model promotion, broker access, order submission, or risk-control bypass.
Candidates must still pass time-series leakage controls, purged/embargoed
validation, calibration, cost-aware expected value, independent holdout,
portfolio risk, reconciliation, authorization, HALTED, and kill-switch gates.
