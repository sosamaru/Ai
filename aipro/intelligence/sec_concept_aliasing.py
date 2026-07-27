"""Explicit, reviewed SEC XBRL concept aliasing for PAPER filing analysis.

This module never infers aliases from text similarity. It applies only CIK-scoped,
operator-reviewed rules and fails closed on ambiguity, unsupported units, transitive
mappings, or canonical fact collisions. It never contacts a broker, submits an order,
promotes a model, or grants execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any, Mapping, Sequence

from aipro.intelligence.sec_edgar import SecFilingEvent
from aipro.intelligence.sec_filing_analysis import (
    ExtractedFilingText,
    FactComparison,
    HistoricalOutcomeReport,
    MaterialityAssessment,
    PriceObservation,
    XbrlExtraction,
    XbrlFact,
    evaluate_historical_outcomes,
    extract_filing_text,
    score_filing_materiality,
)


_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._-]{0,127}$")
_UNIT_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9._/-]{0,63}$")
_MAX_ALIAS_RULES = 500
_MAX_ALLOWED_UNITS = 16


@dataclass(frozen=True, slots=True)
class ConceptAliasRule:
    """One reviewed issuer-specific XBRL concept mapping."""

    cik: str
    source_taxonomy: str
    source_concept: str
    canonical_taxonomy: str
    canonical_concept: str
    allowed_units: tuple[str, ...]
    reviewer: str
    reviewed_at_utc: str
    reason: str


@dataclass(frozen=True, slots=True)
class ConceptAliasRegistry:
    """Validated deterministic collection of explicit alias rules."""

    rules: tuple[ConceptAliasRule, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AppliedConceptAlias:
    cik: str
    source_taxonomy: str
    source_concept: str
    canonical_taxonomy: str
    canonical_concept: str
    unit: str
    matched_fact_count: int
    current_fact_count: int
    rule_fingerprint: str
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AliasAwareXbrlExtraction:
    extraction: XbrlExtraction
    registry_fingerprint: str
    applied_aliases: tuple[AppliedConceptAlias, ...]
    fingerprint: str
    paper_only: bool = True
    grants_execution_authority: bool = False


@dataclass(frozen=True, slots=True)
class AliasAwareFilingAnalysisReport:
    event_fingerprint: str
    text: ExtractedFilingText
    xbrl: AliasAwareXbrlExtraction
    materiality: MaterialityAssessment
    outcomes: HistoricalOutcomeReport | None
    fingerprint: str
    paper_only: bool = True
    grants_execution_authority: bool = False


def build_concept_alias_registry(
    rules: Sequence[ConceptAliasRule],
    *,
    maximum_rules: int = _MAX_ALIAS_RULES,
) -> ConceptAliasRegistry:
    """Validate reviewed aliases and return deterministic immutable evidence."""

    if not 1 <= maximum_rules <= _MAX_ALIAS_RULES:
        raise ValueError("maximum_rules outside reviewed bounds")
    if not rules:
        raise ValueError("at least one concept alias rule is required")
    if len(rules) > maximum_rules:
        raise ValueError("concept alias rules exceed the configured limit")

    normalized: list[ConceptAliasRule] = []
    source_keys: set[tuple[str, str, str]] = set()
    source_nodes_by_cik: dict[str, set[tuple[str, str]]] = {}

    for rule in rules:
        current = _normalize_rule(rule)
        source_key = (current.cik, current.source_taxonomy, current.source_concept)
        if source_key in source_keys:
            raise ValueError("duplicate or ambiguous concept alias source")
        source_keys.add(source_key)
        source_nodes_by_cik.setdefault(current.cik, set()).add(
            (current.source_taxonomy, current.source_concept)
        )
        normalized.append(current)

    for rule in normalized:
        target = (rule.canonical_taxonomy, rule.canonical_concept)
        if target in source_nodes_by_cik[rule.cik]:
            raise ValueError("transitive or cyclic concept aliases are not allowed")

    ordered = tuple(
        sorted(
            normalized,
            key=lambda item: (
                item.cik,
                item.source_taxonomy,
                item.source_concept,
                item.canonical_taxonomy,
                item.canonical_concept,
                item.allowed_units,
                item.reviewed_at_utc,
                item.reviewer,
                item.reason,
            ),
        )
    )
    return ConceptAliasRegistry(
        rules=ordered,
        fingerprint=_fingerprint({"rules": [asdict(item) for item in ordered]}),
    )


def extract_xbrl_facts_with_aliases(
    event: SecFilingEvent,
    companyfacts_payload: Mapping[str, Any],
    registry: ConceptAliasRegistry,
    *,
    maximum_current_facts: int = 500,
    maximum_total_facts: int = 50_000,
) -> AliasAwareXbrlExtraction:
    """Extract and compare XBRL facts after explicit reviewed canonicalization."""

    if not 1 <= maximum_current_facts <= 5_000:
        raise ValueError("maximum_current_facts outside reviewed bounds")
    if not 1 <= maximum_total_facts <= 200_000:
        raise ValueError("maximum_total_facts outside reviewed bounds")
    validated_registry = build_concept_alias_registry(registry.rules)
    if validated_registry.fingerprint != registry.fingerprint:
        raise ValueError("concept alias registry fingerprint mismatch")

    cik = _normalize_cik(companyfacts_payload.get("cik"))
    event_cik = _normalize_cik(event.cik)
    if cik != event_cik:
        raise ValueError("Company Facts CIK does not match the filing event")
    facts_root = companyfacts_payload.get("facts")
    if not isinstance(facts_root, Mapping):
        raise ValueError("Company Facts payload is missing facts")

    rules_by_source = {
        (rule.source_taxonomy, rule.source_concept): rule
        for rule in validated_registry.rules
        if rule.cik == cik
    }
    if not rules_by_source:
        raise ValueError("concept alias registry has no rules for the filing CIK")
    normalized_facts: list[XbrlFact] = []
    application_counts: dict[
        tuple[str, str, str, str, str, str, str], list[int]
    ] = {}
    canonical_identity_values: dict[tuple[Any, ...], str] = {}

    observed_count = 0
    for taxonomy, concepts in facts_root.items():
        if not isinstance(taxonomy, str) or not isinstance(concepts, Mapping):
            continue
        for concept, concept_payload in concepts.items():
            if not isinstance(concept, str) or not isinstance(concept_payload, Mapping):
                continue
            units = concept_payload.get("units")
            if not isinstance(units, Mapping):
                continue
            rule = rules_by_source.get((taxonomy, concept))
            for unit, records in units.items():
                if not isinstance(unit, str) or not isinstance(records, list):
                    continue
                if rule is not None and unit not in rule.allowed_units:
                    raise ValueError("alias source encountered with an unapproved unit")
                for record in records:
                    observed_count += 1
                    if observed_count > maximum_total_facts:
                        raise RuntimeError("Company Facts records exceed the configured limit")
                    fact = _normalize_fact(taxonomy, concept, unit, record)
                    if fact is None:
                        continue
                    canonical = fact
                    if rule is not None:
                        canonical = XbrlFact(
                            taxonomy=rule.canonical_taxonomy,
                            concept=rule.canonical_concept,
                            unit=fact.unit,
                            value=fact.value,
                            start=fact.start,
                            end=fact.end,
                            filed=fact.filed,
                            form=fact.form,
                            accession_number=fact.accession_number,
                            fiscal_year=fact.fiscal_year,
                            fiscal_period=fact.fiscal_period,
                            frame=fact.frame,
                        )
                        rule_fingerprint = _fingerprint(asdict(rule))
                        application_key = (
                            cik,
                            rule.source_taxonomy,
                            rule.source_concept,
                            rule.canonical_taxonomy,
                            rule.canonical_concept,
                            fact.unit,
                            rule_fingerprint,
                        )
                        counts = application_counts.setdefault(application_key, [0, 0])
                        counts[0] += 1
                        if (
                            fact.accession_number == event.accession_number
                            and fact.form == event.form
                        ):
                            counts[1] += 1

                    identity = (
                        canonical.taxonomy,
                        canonical.concept,
                        canonical.unit,
                        canonical.accession_number,
                        canonical.start,
                        canonical.end,
                        canonical.filed,
                        canonical.form,
                        canonical.fiscal_year,
                        canonical.fiscal_period,
                        canonical.frame,
                    )
                    previous_value = canonical_identity_values.get(identity)
                    if previous_value is not None and previous_value != canonical.value:
                        raise ValueError("canonical concept alias produced conflicting facts")
                    if previous_value is None:
                        canonical_identity_values[identity] = canonical.value
                        normalized_facts.append(canonical)

    current = [
        fact
        for fact in normalized_facts
        if fact.accession_number == event.accession_number and fact.form == event.form
    ]
    current.sort(
        key=lambda fact: (
            fact.taxonomy,
            fact.concept,
            fact.unit,
            fact.end,
            fact.value,
        )
    )
    if len(current) > maximum_current_facts:
        raise RuntimeError("current filing facts exceed the configured limit")

    history_by_key: dict[tuple[str, str, str], list[XbrlFact]] = {}
    for fact in normalized_facts:
        history_by_key.setdefault(
            (fact.taxonomy, fact.concept, fact.unit), []
        ).append(fact)

    comparisons: list[FactComparison] = []
    for fact in current:
        candidates = [
            other
            for other in history_by_key[(fact.taxonomy, fact.concept, fact.unit)]
            if other.end < fact.end
            and other.accession_number != fact.accession_number
            and other.form in {"10-K", "10-K/A", "10-Q", "10-Q/A"}
        ]
        if not candidates:
            continue
        previous = max(
            candidates,
            key=lambda item: (item.end, item.filed, item.accession_number),
        )
        comparisons.append(_compare_facts(fact, previous))
    comparisons.sort(key=lambda item: (item.taxonomy, item.concept, item.unit))

    eligible = bool(current)
    reason = None if eligible else "NO_MATCHING_XBRL_FACTS"
    extraction_payload = {
        "cik": cik,
        "accession_number": event.accession_number,
        "current": [asdict(fact) for fact in current],
        "comparisons": [asdict(item) for item in comparisons],
        "eligible": eligible,
        "ineligible_reason": reason,
    }
    extraction = XbrlExtraction(
        cik=cik,
        accession_number=event.accession_number,
        current_facts=tuple(current),
        comparisons=tuple(comparisons),
        eligible=eligible,
        ineligible_reason=reason,
        fingerprint=_fingerprint(extraction_payload),
    )

    applied_aliases = tuple(
        _build_applied_alias(key, counts)
        for key, counts in sorted(application_counts.items())
    )
    payload = {
        "extraction_fingerprint": extraction.fingerprint,
        "registry_fingerprint": validated_registry.fingerprint,
        "applied_aliases": [asdict(item) for item in applied_aliases],
        "paper_only": True,
        "grants_execution_authority": False,
    }
    return AliasAwareXbrlExtraction(
        extraction=extraction,
        registry_fingerprint=validated_registry.fingerprint,
        applied_aliases=applied_aliases,
        fingerprint=_fingerprint(payload),
    )


def build_alias_aware_filing_analysis_report(
    event: SecFilingEvent,
    *,
    filing_html: str,
    companyfacts_payload: Mapping[str, Any],
    alias_registry: ConceptAliasRegistry,
    prices: Sequence[PriceObservation] | None = None,
    benchmark_prices: Sequence[PriceObservation] | None = None,
    horizons: Sequence[int] = (1, 5, 20),
) -> AliasAwareFilingAnalysisReport:
    """Build deterministic PAPER analysis using reviewed alias evidence."""

    text = extract_filing_text(event, filing_html)
    xbrl = extract_xbrl_facts_with_aliases(
        event,
        companyfacts_payload,
        alias_registry,
    )
    materiality = score_filing_materiality(event, text, xbrl.extraction)
    outcomes = (
        evaluate_historical_outcomes(
            event,
            prices,
            horizons=horizons,
            benchmark_prices=benchmark_prices,
        )
        if prices is not None
        else None
    )
    payload = {
        "event_fingerprint": event.fingerprint,
        "text_fingerprint": text.fingerprint,
        "alias_aware_xbrl_fingerprint": xbrl.fingerprint,
        "materiality_fingerprint": materiality.fingerprint,
        "outcome_fingerprint": outcomes.fingerprint if outcomes else None,
        "paper_only": True,
        "grants_execution_authority": False,
    }
    return AliasAwareFilingAnalysisReport(
        event_fingerprint=event.fingerprint,
        text=text,
        xbrl=xbrl,
        materiality=materiality,
        outcomes=outcomes,
        fingerprint=_fingerprint(payload),
    )


def _normalize_rule(rule: ConceptAliasRule) -> ConceptAliasRule:
    cik = _normalize_cik(rule.cik)
    source_taxonomy = _normalize_identifier(rule.source_taxonomy, "source_taxonomy")
    source_concept = _normalize_identifier(rule.source_concept, "source_concept")
    canonical_taxonomy = _normalize_identifier(
        rule.canonical_taxonomy, "canonical_taxonomy"
    )
    canonical_concept = _normalize_identifier(
        rule.canonical_concept, "canonical_concept"
    )
    if (source_taxonomy, source_concept) == (
        canonical_taxonomy,
        canonical_concept,
    ):
        raise ValueError("concept alias source and target must differ")

    allowed_units = tuple(sorted({str(unit).strip() for unit in rule.allowed_units}))
    if not allowed_units or len(allowed_units) > _MAX_ALLOWED_UNITS:
        raise ValueError("allowed_units must contain 1 to 16 unique units")
    if any(not _UNIT_PATTERN.fullmatch(unit) for unit in allowed_units):
        raise ValueError("allowed_units contain an invalid identifier")

    reviewer = str(rule.reviewer).strip()
    reason = str(rule.reason).strip()
    if not 1 <= len(reviewer) <= 128:
        raise ValueError("reviewer must contain 1 to 128 characters")
    if not 10 <= len(reason) <= 1_000:
        raise ValueError("reason must contain 10 to 1000 characters")

    try:
        reviewed_at = datetime.fromisoformat(str(rule.reviewed_at_utc).strip())
    except ValueError as exc:
        raise ValueError("reviewed_at_utc must be a valid timestamp") from exc
    if reviewed_at.tzinfo is None:
        raise ValueError("reviewed_at_utc must be timezone-aware")
    reviewed_at_utc = reviewed_at.astimezone(UTC).replace(microsecond=0).isoformat()

    return ConceptAliasRule(
        cik=cik,
        source_taxonomy=source_taxonomy,
        source_concept=source_concept,
        canonical_taxonomy=canonical_taxonomy,
        canonical_concept=canonical_concept,
        allowed_units=allowed_units,
        reviewer=reviewer,
        reviewed_at_utc=reviewed_at_utc,
        reason=reason,
    )


def _normalize_cik(raw: Any) -> str:
    value = str(raw).strip()
    if not value.isdigit() or len(value) > 10:
        raise ValueError("CIK must be a numeric value up to 10 digits")
    return value.lstrip("0") or "0"


def _normalize_identifier(raw: Any, field: str) -> str:
    value = str(raw).strip()
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"{field} contains an invalid identifier")
    return value


def _normalize_fact(
    taxonomy: str,
    concept: str,
    unit: str,
    record: Any,
) -> XbrlFact | None:
    if not isinstance(record, Mapping):
        return None
    accession = str(record.get("accn", "")).strip()
    end = str(record.get("end", "")).strip()
    filed = str(record.get("filed", "")).strip()
    form = str(record.get("form", "")).strip().upper()
    raw_value = record.get("val")
    if not accession or not end or not filed or not form or isinstance(raw_value, bool):
        return None
    try:
        value = Decimal(str(raw_value))
    except (InvalidOperation, ValueError):
        return None
    if not value.is_finite():
        return None
    try:
        datetime.fromisoformat(end)
        datetime.fromisoformat(filed)
    except ValueError:
        return None
    fiscal_year = record.get("fy")
    if isinstance(fiscal_year, bool) or not isinstance(fiscal_year, int):
        fiscal_year = None
    fiscal_period = record.get("fp")
    frame = record.get("frame")
    return XbrlFact(
        taxonomy=taxonomy,
        concept=concept,
        unit=unit,
        value=format(value, "f"),
        start=str(record.get("start")).strip() if record.get("start") else None,
        end=end,
        filed=filed,
        form=form,
        accession_number=accession,
        fiscal_year=fiscal_year,
        fiscal_period=str(fiscal_period).strip() if fiscal_period else None,
        frame=str(frame).strip() if frame else None,
    )


def _compare_facts(current: XbrlFact, previous: XbrlFact) -> FactComparison:
    current_value = current.decimal_value
    previous_value = previous.decimal_value
    change_ratio: float | None = None
    if previous_value != 0:
        ratio = (current_value - previous_value) / abs(previous_value)
        if ratio.is_finite():
            change_ratio = float(ratio)
    sign_reversal = (
        current_value < 0 < previous_value
        or previous_value < 0 < current_value
    )
    return FactComparison(
        taxonomy=current.taxonomy,
        concept=current.concept,
        unit=current.unit,
        current_value=current.value,
        previous_value=previous.value,
        current_end=current.end,
        previous_end=previous.end,
        change_ratio=change_ratio,
        sign_reversal=sign_reversal,
    )


def _build_applied_alias(
    key: tuple[str, str, str, str, str, str, str],
    counts: list[int],
) -> AppliedConceptAlias:
    (
        cik,
        source_taxonomy,
        source_concept,
        canonical_taxonomy,
        canonical_concept,
        unit,
        rule_fingerprint,
    ) = key
    payload = {
        "cik": cik,
        "source_taxonomy": source_taxonomy,
        "source_concept": source_concept,
        "canonical_taxonomy": canonical_taxonomy,
        "canonical_concept": canonical_concept,
        "unit": unit,
        "matched_fact_count": counts[0],
        "current_fact_count": counts[1],
        "rule_fingerprint": rule_fingerprint,
    }
    return AppliedConceptAlias(
        **payload,
        fingerprint=_fingerprint(payload),
    )


def _fingerprint(payload: Mapping[str, Any]) -> str:
    return sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "AliasAwareFilingAnalysisReport",
    "AliasAwareXbrlExtraction",
    "AppliedConceptAlias",
    "ConceptAliasRegistry",
    "ConceptAliasRule",
    "build_alias_aware_filing_analysis_report",
    "build_concept_alias_registry",
    "extract_xbrl_facts_with_aliases",
]
