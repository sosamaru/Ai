# Domain-isolated PAPER strategy validation

## Purpose

`aipro.intelligence.paper_strategy_validation` combines four existing research-only components into one deterministic validation path:

1. domain-specific regime classification
2. domain-specific strategy selection
3. risk-adjusted expected-value and volatility sizing
4. deterministic execution-cost simulation

The result is immutable PAPER research evidence. It is not an order instruction.

## Eligibility rules

A candidate is eligible only when all of the following hold:

- feature, strategy, forecast, and market inputs belong to one domain
- regime confidence is sufficient and the strategy pipeline does not abstain
- the forecast has positive cost-aware expected value and a positive bounded Kelly edge
- risk, volatility, uncertainty, and maximum-position caps permit a non-zero PAPER size
- the simulated provider is available
- the hypothetical order is fully filled within the configured participation limit
- estimated round-trip execution costs do not eliminate the remaining edge

Any failure produces an explicit ineligible reason and stops the path fail-closed.

## Domain isolation

Crypto uses `crypto`; U.S. stocks use `us_stocks`. The orchestration maps the regime module's U.S.-stock enum to the sizing and execution domain without sharing capital, baselines, symbols, candidates, model IDs, feature fingerprints, or evidence records.

## Evidence lineage

Every result includes:

- regime and selection fingerprints
- sizing and execution fingerprints when those stages run
- model ID
- source feature SHA-256 fingerprint
- final validation SHA-256 fingerprint
- an explicit `paper_only` marker

Changing model lineage, feature lineage, market assumptions, strategy selection, sizing, or simulated execution changes the final fingerprint.

## Hard safety boundary

This module has no broker client, credentials, network calls, order endpoint, cancellation path, retry path, LIVE authorization, or ability to change `TradingApplication` state. It cannot bypass readiness, reconciliation, freshness, portfolio limits, HALTED state, kill switches, or independent live-readiness review.

A positive result means only that one hypothetical PAPER evaluation passed the configured deterministic rules. It does not prove profitability and does not authorize real trading.
