# Combined PAPER Feature Vector

## Purpose

`aipro.intelligence.combined_features` combines already-normalized news, FRED macro, SEC filing, and OHLCV market snapshots into one deterministic, versioned feature vector for later offline training and PAPER validation.

The current schema is `paper-feature-vector-v1`. Feature order is fixed by `FEATURE_NAMES`; downstream datasets and models must store and verify both the schema version and fingerprint.

## Safety boundary

- This module has no broker, account, balance, position, authorization, or order endpoint.
- It cannot enable LIVE mode or bypass readiness and risk gates.
- Output is evidence for research and PAPER evaluation only.
- Features are descriptive inputs, not guaranteed predictions or direct buy/sell commands.

## Fail-closed behavior

The vector becomes ineligible when a required component is ineligible, symbols disagree, a component timestamp is in the future, or component timestamps exceed the configured skew tolerance.

Individual source fingerprints are embedded in the combined fingerprint so any source-data, policy, schema, or value change produces new evidence.

## Limitations

- The V1 vector uses transparent baseline features and no learned source weights.
- SEC features count structural filing categories; they do not yet parse filing text or XBRL facts.
- Missing optional spread values are encoded as zero and must be accompanied by source evidence during research.
- Eligibility only validates structural readiness. It does not demonstrate profitability.

## Next validation

Use the versioned vector to build leak-resistant chronological datasets, then implement walk-forward training with strictly out-of-sample evaluation and separate crypto and US-stock validation.
