# Domain-isolated regime and strategy pipelines

## Purpose

This module provides deterministic PAPER-research classification and strategy selection for two independent domains:

- cryptocurrency
- U.S. stocks

It does not merge balances, baselines, positions, strategies, features, or approvals across those domains.

## Regimes

The classifier can emit:

- trend up
- trend down
- range
- high volatility
- low volatility
- risk off
- overheated
- unknown

Risk-off and high-volatility conditions take priority over ordinary trend classifications. Unknown or low-confidence classifications cause abstention rather than forced selection.

## Strategy governance

A strategy must explicitly declare its supported domain and regimes. Selection uses expected value reduced by model uncertainty. Disabled strategies, foreign-domain strategies, unsupported regimes, non-positive adjusted scores, and low-confidence regimes are rejected.

## Safety boundary

The output is PAPER research evidence only. It cannot submit, cancel, replace, or retry an order and cannot bypass:

- account and baseline isolation
- portfolio limits
- risk sizing
- readiness evidence
- data freshness
- reconciliation
- LIVE authorization
- HALTED state
- kill switches

The deterministic fingerprint is an audit identifier, not proof of profitability or live readiness.
