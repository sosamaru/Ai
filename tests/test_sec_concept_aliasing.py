from __future__ import annotations

from dataclasses import replace
from math import isclose

import pytest

from aipro.intelligence.sec_concept_aliasing import (
    ConceptAliasRegistry,
    ConceptAliasRule,
    build_alias_aware_filing_analysis_report,
    build_concept_alias_registry,
    extract_xbrl_facts_with_aliases,
)
from aipro.intelligence.sec_edgar import FilingEventType, SecFilingEvent


_ACCESSION = "0000320193-26-000001"
_CANONICAL_REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"


def _event(*, cik: str = "320193") -> SecFilingEvent:
    return SecFilingEvent(
        cik=cik,
        company_name="Example Corp",
        accession_number=_ACCESSION,
        form="10-Q",
        filed_at_utc="2026-04-01T00:00:00+00:00",
        report_date="2026-03-31",
        primary_document="example.htm",
        event_type=FilingEventType.QUARTERLY_REPORT,
        sec_url=(
            "https://www.sec.gov/Archives/edgar/data/320193/"
            "000032019326000001/example.htm"
        ),
        items=("2.02",),
    )


def _rule(
    *,
    cik: str = "320193",
    source_taxonomy: str = "example",
    source_concept: str = "CloudPlatformRevenue",
    canonical_taxonomy: str = "us-gaap",
    canonical_concept: str = _CANONICAL_REVENUE,
    allowed_units: tuple[str, ...] = ("USD",),
) -> ConceptAliasRule:
    return ConceptAliasRule(
        cik=cik,
        source_taxonomy=source_taxonomy,
        source_concept=source_concept,
        canonical_taxonomy=canonical_taxonomy,
        canonical_concept=canonical_concept,
        allowed_units=allowed_units,
        reviewer="sec-review@example.com",
        reviewed_at_utc="2026-07-27T10:00:00+09:00",
        reason=(
            "Reviewed against the issuer filing presentation and the standard "
            "revenue recognition concept."
        ),
    )


def _record(
    *,
    accession: str,
    start: str,
    end: str,
    value: int,
    filed: str,
    fiscal_year: int,
) -> dict:
    return {
        "start": start,
        "end": end,
        "val": value,
        "accn": accession,
        "fy": fiscal_year,
        "fp": "Q1",
        "form": "10-Q",
        "filed": filed,
        "frame": f"CY{fiscal_year}Q1",
    }


def _companyfacts(
    *,
    current_unit: str = "USD",
    include_conflicting_standard_current: bool = False,
) -> dict:
    standard_records = [
        _record(
            accession="0000320193-25-000001",
            start="2025-01-01",
            end="2025-03-31",
            value=100,
            filed="2025-04-01",
            fiscal_year=2025,
        )
    ]
    if include_conflicting_standard_current:
        standard_records.append(
            _record(
                accession=_ACCESSION,
                start="2026-01-01",
                end="2026-03-31",
                value=150,
                filed="2026-04-01",
                fiscal_year=2026,
            )
        )
    return {
        "cik": 320193,
        "entityName": "Example Corp",
        "facts": {
            "us-gaap": {
                _CANONICAL_REVENUE: {
                    "units": {
                        "USD": standard_records,
                    }
                }
            },
            "example": {
                "CloudPlatformRevenue": {
                    "units": {
                        current_unit: [
                            _record(
                                accession=_ACCESSION,
                                start="2026-01-01",
                                end="2026-03-31",
                                value=160,
                                filed="2026-04-01",
                                fiscal_year=2026,
                            )
                        ]
                    }
                }
            },
        },
    }


def _html() -> str:
    return """
    <html><body>
      <p>Item 2.02 Results of Operations.</p>
      <p>The company reported updated revenue, liquidity, guidance, and
      operating performance. This reviewed visible text is deliberately long
      enough to satisfy the evidence threshold without relying only on XBRL.</p>
    </body></html>
    """


def test_reviewed_alias_bridges_extension_to_prior_standard_fact():
    registry = build_concept_alias_registry((_rule(),))
    result = extract_xbrl_facts_with_aliases(
        _event(),
        _companyfacts(),
        registry,
    )

    assert result.extraction.eligible
    assert len(result.extraction.current_facts) == 1
    assert result.extraction.current_facts[0].taxonomy == "us-gaap"
    assert result.extraction.current_facts[0].concept == _CANONICAL_REVENUE
    assert len(result.extraction.comparisons) == 1
    assert isclose(result.extraction.comparisons[0].change_ratio or 0.0, 0.6)
    assert result.applied_aliases[0].matched_fact_count == 1
    assert result.applied_aliases[0].current_fact_count == 1
    assert result.paper_only
    assert not result.grants_execution_authority


def test_registry_is_normalized_and_deterministic():
    first = build_concept_alias_registry(
        (
            replace(
                _rule(),
                cik="0000320193",
                allowed_units=("USD/shares", "USD"),
            ),
        )
    )
    second = build_concept_alias_registry(
        (
            replace(
                _rule(),
                allowed_units=("USD", "USD/shares"),
                reviewed_at_utc="2026-07-27T01:00:00+00:00",
            ),
        )
    )

    assert first.rules == second.rules
    assert first.rules[0].cik == "320193"
    assert first.rules[0].allowed_units == ("USD", "USD/shares")
    assert first.fingerprint == second.fingerprint


def test_duplicate_and_transitive_aliases_fail_closed():
    duplicate = replace(_rule(), canonical_concept="SalesRevenueNet")
    with pytest.raises(ValueError, match="duplicate|ambiguous"):
        build_concept_alias_registry((_rule(), duplicate))

    second = _rule(
        source_taxonomy="us-gaap",
        source_concept=_CANONICAL_REVENUE,
        canonical_concept="SalesRevenueNet",
    )
    with pytest.raises(ValueError, match="transitive|cyclic"):
        build_concept_alias_registry((_rule(), second))


def test_unapproved_unit_fails_closed():
    registry = build_concept_alias_registry((_rule(),))
    with pytest.raises(ValueError, match="unapproved unit"):
        extract_xbrl_facts_with_aliases(
            _event(),
            _companyfacts(current_unit="shares"),
            registry,
        )


def test_canonical_fact_collision_fails_closed():
    registry = build_concept_alias_registry((_rule(),))
    with pytest.raises(ValueError, match="conflicting facts"):
        extract_xbrl_facts_with_aliases(
            _event(),
            _companyfacts(include_conflicting_standard_current=True),
            registry,
        )


def test_registry_fingerprint_tampering_and_missing_cik_rules_fail_closed():
    registry = build_concept_alias_registry((_rule(),))
    tampered = ConceptAliasRegistry(
        rules=registry.rules,
        fingerprint="0" * 64,
    )
    with pytest.raises(ValueError, match="fingerprint"):
        extract_xbrl_facts_with_aliases(_event(), _companyfacts(), tampered)

    other_issuer = build_concept_alias_registry((_rule(cik="1"),))
    with pytest.raises(ValueError, match="no rules"):
        extract_xbrl_facts_with_aliases(
            _event(),
            _companyfacts(),
            other_issuer,
        )


def test_alias_aware_report_is_deterministic_and_non_authoritative():
    registry = build_concept_alias_registry((_rule(),))
    first = build_alias_aware_filing_analysis_report(
        _event(),
        filing_html=_html(),
        companyfacts_payload=_companyfacts(),
        alias_registry=registry,
    )
    second = build_alias_aware_filing_analysis_report(
        _event(),
        filing_html=_html(),
        companyfacts_payload=_companyfacts(),
        alias_registry=registry,
    )

    assert first.fingerprint == second.fingerprint
    assert first.xbrl.fingerprint == second.xbrl.fingerprint
    assert first.materiality.evidence_sufficient
    assert first.paper_only
    assert not first.grants_execution_authority


def test_invalid_review_evidence_fails_closed():
    with pytest.raises(ValueError, match="timezone-aware"):
        build_concept_alias_registry(
            (replace(_rule(), reviewed_at_utc="2026-07-27T01:00:00"),)
        )
    with pytest.raises(ValueError, match="reason"):
        build_concept_alias_registry((replace(_rule(), reason="too short"),))
