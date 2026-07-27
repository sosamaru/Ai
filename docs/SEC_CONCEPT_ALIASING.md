# Reviewed SEC Concept Aliasing

## Purpose

`aipro.intelligence.sec_concept_aliasing` adds an opt-in PAPER analysis path for
issuer-specific SEC Company Facts concepts. It exists because an issuer may report
a current fact under a custom taxonomy while an economically comparable prior fact
was reported under a standard taxonomy.

The module does not guess semantic equivalence. Every mapping must be explicitly
reviewed and scoped to one CIK.

## Safety boundary

This feature:

- reads already supplied SEC Company Facts evidence;
- preserves the existing default `sec_filing_analysis` behavior;
- produces deterministic PAPER research evidence only;
- never contacts a broker or order endpoint;
- never mutates model champion, authorization, HALTED, kill-switch, account, or
  portfolio state;
- never grants execution authority;
- does not change `run.py -> telegram.py -> main.py -> TradingApplication`.

Automatic text similarity, embedding similarity, LLM-generated mappings, taxonomy
name heuristics, and cross-issuer alias reuse are intentionally prohibited.

## Rule contract

Each `ConceptAliasRule` requires:

- normalized issuer CIK;
- exact source taxonomy and concept;
- exact canonical taxonomy and concept;
- one or more explicitly allowed units;
- reviewer identity;
- timezone-aware review timestamp;
- a concrete review reason.

The registry sorts and fingerprints normalized rules. A consumer must use
`build_concept_alias_registry`; a manually altered registry fingerprint is rejected.

## Fail-closed behavior

The feature rejects:

- duplicate mappings for the same CIK/source taxonomy/source concept;
- transitive or cyclic mappings;
- source and target equality;
- invalid identifiers or missing review evidence;
- a source concept observed under an unapproved unit;
- a registry with no rule for the filing CIK;
- a Company Facts CIK mismatch;
- excessive rule, total-fact, or current-fact counts;
- conflicting facts that collapse onto the same canonical identity;
- malformed or non-finite fact values and invalid dates.

Exact duplicate facts with the same canonical identity and value are deduplicated.
Conflicting values for that identity fail closed.

## Canonical comparison behavior

The alias-aware extractor canonicalizes both current and historical facts before
building prior-period comparisons. This allows a reviewed issuer extension in the
current filing to be compared with a prior standard concept when taxonomy, concept,
and unit become identical after canonicalization.

Every applied mapping records:

- source and canonical identities;
- unit;
- total matched fact count;
- current-filing matched fact count;
- rule fingerprint;
- deterministic application fingerprint.

The wrapper carries the registry fingerprint and explicit
`paper_only = true` / `grants_execution_authority = false` markers.

## Example

```python
from aipro.intelligence.sec_concept_aliasing import (
    ConceptAliasRule,
    build_alias_aware_filing_analysis_report,
    build_concept_alias_registry,
)

registry = build_concept_alias_registry(
    (
        ConceptAliasRule(
            cik="320193",
            source_taxonomy="issuer",
            source_concept="CloudPlatformRevenue",
            canonical_taxonomy="us-gaap",
            canonical_concept=(
                "RevenueFromContractWithCustomerExcludingAssessedTax"
            ),
            allowed_units=("USD",),
            reviewer="reviewer@example.com",
            reviewed_at_utc="2026-07-27T01:00:00+00:00",
            reason=(
                "Reviewed against the filing presentation and the standard "
                "revenue recognition concept."
            ),
        ),
    )
)

report = build_alias_aware_filing_analysis_report(
    event,
    filing_html=filing_html,
    companyfacts_payload=companyfacts_payload,
    alias_registry=registry,
)
```

## Limitations

A reviewed alias proves only that a specific operator approved the mapping record.
It does not prove the accounting interpretation is correct. Fingerprints prove
deterministic content continuity, not reviewer identity or external attestation.

The feature does not discover aliases automatically, perform accounting-policy
interpretation, resolve dimensional XBRL contexts, or guarantee that two similarly
named concepts are economically interchangeable. Independent review remains
mandatory before a rule is used in research.
