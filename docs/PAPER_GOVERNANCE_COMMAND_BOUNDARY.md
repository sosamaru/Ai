# PAPER Governance Command Boundary

## Purpose

This boundary converts a reviewed champion-monitoring decision into an immutable PAPER command proposal. It separates monitoring, human approval, command construction, explicit confirmation, registry mutation, and any later model-serving process.

## Required evidence

A command proposal is created only when:

- monitoring and approval evidence are PAPER-only
- the approval outcome is `approve`
- domains, monitoring fingerprints, and recommendations match exactly
- the approval explicitly grants no execution authority
- the recommendation is replacement review, rollback review, or deactivation
- replacement names a challenger
- rollback names an explicit registry event target

`hold` and `abstain` cannot produce registry-changing commands.

## Explicit confirmation

A proposal is unconfirmed by default. Confirmation requires the exact phrase `APPLY PAPER GOVERNANCE` and produces a new deterministic fingerprint. Confirmation still does not mutate the champion registry.

## Safety boundary

The module does not activate, replace, roll back, or deactivate registry state. It does not load or serve a model, contact a broker, create a PAPER or LIVE order, change authorization, override HALTED state, or bypass readiness, reconciliation, portfolio-risk, freshness, or kill-switch gates.

A separate registry application adapter must verify the confirmed command again before any append-only registry event is created. No broker or execution authority may be attached to that adapter.
