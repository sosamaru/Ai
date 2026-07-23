# PAPER Execution Simulator Safety

## Purpose

`aipro.intelligence.execution_simulator` estimates how a hypothetical order may be affected by execution frictions before any broker integration is considered.

It models:

- explicit fees
- half-spread cost
- configured baseline slippage
- latency-related adverse movement
- square-root market impact
- liquidity participation limits
- partial fills
- provider outages

## Hard boundary

The simulator has no broker client, credential handling, network calls, order endpoint, cancellation path, or retry authority. Its output is PAPER research evidence only.

A favorable simulated fill must never bypass:

- PAPER/LIVE environment separation
- domain-specific capital and risk limits
- provider freshness and health gates
- duplicate-order protection
- reconciliation requirements
- authorization requirements
- HALTED and kill-switch state
- independent live-readiness review

## Determinism and evidence

Identical validated inputs produce identical outputs and a SHA-256 fingerprint. This supports regression testing, experiment comparison, and append-only research evidence.

## Limitations

The current model is a deterministic approximation, not a reconstructed limit-order book. It does not claim to predict an exact real fill. Parameters must be calibrated independently for crypto and US stocks using domain-specific PAPER observations. Crypto and US-stock requests cannot be combined into one simulation record.

## Failure behavior

Malformed values, invalid domains, impossible participation rates, and non-positive required quantities fail closed. Provider outages return an explicit rejected result with zero simulated fill rather than silently assuming execution.
