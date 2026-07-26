# Purged sequence-model PAPER training

`aipro/research/purged_sequence_runner.py` adds bounded, optional LSTM, GRU, and Transformer-encoder training to the existing purged walk-forward research contract.

## Safety boundary

The runner is PAPER research infrastructure only. It does not persist model binaries, serve inference, contact a broker, submit or cancel orders, change champion state, enable LIVE mode, or grant execution authority.

The normal application path remains unchanged:

`run.py -> telegram.py -> main.py -> TradingApplication`

PyTorch and TensorFlow are optional. Neither package is imported when AiPro starts or when backend availability is inspected. A package is imported only after an operator explicitly runs sequence training with a validated specification.

## Leakage controls

For every purged fold, the runner:

1. reuses the existing overlapping-label purge and post-test embargo evidence;
2. builds a fresh model for the fold;
3. constructs only contiguous sequences whose complete windows belong to the same train or test partition;
4. fits feature means and scales from training sequences only;
5. scores untouched test sequences;
6. records balanced accuracy, Brier score, cost-aware expected value, turnover, sample counts, and SHA-256 evidence.

The strict partition-local sequence rule is intentionally conservative. A test sequence cannot borrow feature rows from the training partition, and a training sequence cannot bridge a purged gap.

## Bounded resources

The reviewed sequence specification already limits hidden size, layer count, dropout, sequence length, batch size, epochs, learning rate, and Transformer attention geometry. The runner adds per-fold limits for:

- training sequence count;
- test sequence count;
- total feature values materialized in a fold.

PyTorch execution is restricted to one CPU thread with deterministic algorithms enabled. TensorFlow seeds are fixed, thread counts are restricted where runtime state permits, operation determinism is requested, and training uses `shuffle=False`.

## Supported models

- PyTorch LSTM
- PyTorch GRU
- PyTorch Transformer encoder with sinusoidal positional encoding
- TensorFlow/Keras LSTM
- TensorFlow/Keras GRU
- TensorFlow/Keras Transformer encoder with learned positional embeddings

Each fold creates a new backend model. No trained model object leaves the runner; only PAPER evaluation evidence is returned.

## Fail-closed conditions

Training stops before producing a report when any of the following occurs:

- crypto and U.S.-stock rows are mixed;
- the sequence specification domain or feature order differs from the dataset;
- a fold cannot form a contiguous partition-local sequence;
- a training fold lacks both target classes;
- a configured resource budget is exceeded;
- the optional backend is unavailable;
- prediction count differs from the number of test sequences;
- a probability is non-finite or outside `[0, 1]`.

## Operational note

Passing unit tests or producing a positive PAPER evaluation does not establish profitability or live readiness. Champion governance, long-duration PAPER evidence, reconciliation, authorization, risk gates, HALTED state, kill switches, and an independent live-readiness decision remain mandatory and separate.
