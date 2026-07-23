# PAPER market feature extraction

## Scope

This module converts validated OHLCV bars into deterministic, broker-neutral PAPER intelligence features.

Included features:

- short- and medium-window return
- realized log-return volatility
- average true range as a percentage of price
- recent-to-baseline volume ratio
- average quote volume
- optional average bid-ask spread
- a transparent illiquidity proxy
- a bounded trend score
- SHA-256 snapshot fingerprint

## Fail-closed rules

A snapshot is ineligible when market data is absent, insufficient, stale, timestamped in the future, duplicated, or contains excessive zero-volume bars. Invalid OHLC relationships and non-finite values are rejected before feature generation.

## Safety boundary

The output is data only. It cannot submit orders, change balances or positions, reset daily baselines, alter authorization, release HALTED state, or bypass provider-health and risk gates.

The trend and illiquidity values are transparent baseline features, not profitability claims. They require later walk-forward evaluation, ablation analysis, drift monitoring, and independent PAPER validation before they may influence position sizing.
