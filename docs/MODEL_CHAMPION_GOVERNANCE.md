# PAPER Model Champion Governance

AiPro may rank only candidates that already passed the classical model evaluation gate. Champion selection is a separate, stricter decision and remains PAPER-only.

## Fail-closed rules

- Crypto and US-stock candidates cannot be mixed.
- Candidate names must be unique.
- Rejected candidates are excluded.
- Calibration must remain within the configured Brier-score ceiling.
- Expected value must remain positive unless an explicit research policy says otherwise.
- When two or more candidates are eligible, the leader must exceed the runner-up by both a minimum total score margin and a minimum expected-value margin.
- Indecisive evidence returns no approved champion.

## Evidence

Every decision stores the selected candidate fingerprint, challenger fingerprint, policy values, reasons, PAPER-only marker, and a deterministic SHA-256 decision fingerprint.

## Safety boundary

Champion approval does not train, persist, promote, or serve a model. It cannot contact a broker, create an order, enable LIVE mode, bypass authorization, override HALTED state, or replace domain-specific walk-forward and paper-trading evidence. A champion is only a governed research candidate for later PAPER validation.
