"""Deterministic SEC filing text, XBRL, materiality, and outcome analysis.

This module is PAPER intelligence infrastructure only. It reads public SEC evidence,
normalizes bounded inputs, and produces immutable research evidence. It never contacts
a broker, submits an order, promotes a model, or grants execution authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from hashlib import sha256
from html.parser import HTMLParser
import json
import math
import re
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib import request

from aipro.intelligence.sec_edgar import SecFilingEvent


class MaterialityLevel(StrEnum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(frozen=True, slots=True)
class ExtractedFilingText:
    accession_number: str
    form: str
    text: str
    character_count: int
    detected_items: tuple[str, ...]
    signal_terms: tuple[str, ...]
    truncated: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class XbrlFact:
    taxonomy: str
    concept: str
    unit: str
    value: str
    start: str | None
    end: str
    filed: str
    form: str
    accession_number: str
    fiscal_year: int | None
    fiscal_period: str | None
    frame: str | None

    @property
    def decimal_value(self) -> Decimal:
        return Decimal(self.value)


@dataclass(frozen=True, slots=True)
class FactComparison:
    taxonomy: str
    concept: str
    unit: str
    current_value: str
    previous_value: str
    current_end: str
    previous_end: str
    change_ratio: float | None
    sign_reversal: bool


@dataclass(frozen=True, slots=True)
class XbrlExtraction:
    cik: str
    accession_number: str
    current_facts: tuple[XbrlFact, ...]
    comparisons: tuple[FactComparison, ...]
    eligible: bool
    ineligible_reason: str | None
    fingerprint: str


@dataclass(frozen=True, slots=True)
class MaterialityAssessment:
    score: int
    level: MaterialityLevel
    reasons: tuple[str, ...]
    evidence_sufficient: bool
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PriceObservation:
    observed_at_utc: str
    close: float

    def __post_init__(self) -> None:
        observed = datetime.fromisoformat(self.observed_at_utc)
        if observed.tzinfo is None:
            raise ValueError("observed_at_utc must be timezone-aware")
        if not math.isfinite(self.close) or self.close <= 0:
            raise ValueError("close must be finite and positive")


@dataclass(frozen=True, slots=True)
class OutcomePoint:
    horizon: int
    baseline_at_utc: str
    outcome_at_utc: str
    raw_return: float
    benchmark_return: float | None
    abnormal_return: float | None


@dataclass(frozen=True, slots=True)
class HistoricalOutcomeReport:
    accession_number: str
    event_at_utc: str
    outcomes: tuple[OutcomePoint, ...]
    eligible: bool
    ineligible_reason: str | None
    fingerprint: str


@dataclass(frozen=True, slots=True)
class FilingAnalysisReport:
    event_fingerprint: str
    text: ExtractedFilingText
    xbrl: XbrlExtraction
    materiality: MaterialityAssessment
    outcomes: HistoricalOutcomeReport | None
    fingerprint: str
    paper_only: bool = True
    grants_execution_authority: bool = False


_DEFAULT_SIGNAL_TERMS: tuple[str, ...] = (
    "bankruptcy",
    "chapter 11",
    "going concern",
    "restatement",
    "material weakness",
    "cybersecurity incident",
    "data breach",
    "default",
    "delisting",
    "merger",
    "acquisition",
    "tender offer",
    "divestiture",
    "restructuring",
    "impairment",
    "guidance",
    "liquidity",
)

_ITEM_WEIGHTS: Mapping[str, int] = {
    "1.01": 8,
    "1.02": 10,
    "2.01": 14,
    "2.02": 14,
    "2.05": 16,
    "2.06": 14,
    "3.01": 16,
    "4.01": 18,
    "4.02": 20,
    "5.02": 10,
    "7.01": 5,
    "8.01": 6,
}

_FORM_WEIGHTS: Mapping[str, int] = {
    "8-K": 16,
    "8-K/A": 14,
    "10-K": 12,
    "10-K/A": 16,
    "10-Q": 9,
    "10-Q/A": 13,
    "S-1": 18,
    "S-1/A": 16,
    "S-3": 14,
    "S-3/A": 13,
    "424B5": 14,
    "SC 13D": 14,
    "SC 13D/A": 12,
}

_SIGNAL_WEIGHTS: Mapping[str, int] = {
    "bankruptcy": 24,
    "chapter 11": 24,
    "going concern": 18,
    "restatement": 20,
    "material weakness": 16,
    "cybersecurity incident": 18,
    "data breach": 16,
    "default": 16,
    "delisting": 18,
    "merger": 12,
    "acquisition": 10,
    "tender offer": 14,
    "divestiture": 8,
    "restructuring": 10,
    "impairment": 10,
    "guidance": 6,
    "liquidity": 6,
}

_MATERIAL_CONCEPT_HINTS = (
    "revenue",
    "sales",
    "netincomeloss",
    "operatingincomeloss",
    "assets",
    "liabilities",
    "stockholdersequity",
    "cashandcashequivalents",
    "debt",
    "earningspershare",
    "impairment",
    "goodwill",
)


class _VisibleTextParser(HTMLParser):
    _SKIP_TAGS = {"script", "style", "noscript", "svg"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized = tag.lower()
        if normalized in self._SKIP_TAGS:
            self._skip_depth += 1
        elif self._skip_depth == 0 and normalized in {
            "p", "div", "br", "tr", "li", "h1", "h2", "h3", "h4"
        }:
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        normalized = tag.lower()
        if normalized in self._SKIP_TAGS and self._skip_depth:
            self._skip_depth -= 1
        elif self._skip_depth == 0 and normalized in {"p", "div", "tr", "li"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


class SecFilingContentClient:
    """Bounded read-only client for SEC Archives documents and Company Facts."""

    COMPANY_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"

    def __init__(
        self,
        user_agent: str,
        *,
        timeout_seconds: float = 15.0,
        maximum_response_bytes: int = 8_000_000,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        normalized = user_agent.strip()
        if len(normalized) < 10 or "@" not in normalized:
            raise ValueError("SEC user agent must include an application name and contact email")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if not 1_024 <= maximum_response_bytes <= 50_000_000:
            raise ValueError("maximum_response_bytes outside reviewed bounds")
        self.user_agent = normalized
        self.timeout_seconds = timeout_seconds
        self.maximum_response_bytes = maximum_response_bytes
        self._opener = opener or request.urlopen

    def fetch_filing_html(self, sec_url: str) -> str:
        if not sec_url.startswith("https://www.sec.gov/Archives/"):
            raise ValueError("filing URL must target https://www.sec.gov/Archives/")
        raw = self._fetch(sec_url, "text/html,application/xhtml+xml")
        return raw.decode("utf-8", errors="replace")

    def fetch_companyfacts(self, cik: str | int) -> dict[str, Any]:
        value = str(cik).strip()
        if not value.isdigit() or len(value) > 10:
            raise ValueError("CIK must be a numeric value up to 10 digits")
        raw = self._fetch(
            self.COMPANY_FACTS_URL.format(cik=value.zfill(10)),
            "application/json",
        )
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("SEC Company Facts response must be a JSON object")
        return payload

    def _fetch(self, url: str, accept: str) -> bytes:
        req = request.Request(
            url,
            method="GET",
            headers={
                "User-Agent": self.user_agent,
                "Accept": accept,
                "Accept-Encoding": "identity",
            },
        )
        with self._opener(req, timeout=self.timeout_seconds) as response:
            raw = response.read(self.maximum_response_bytes + 1)
        if len(raw) > self.maximum_response_bytes:
            raise RuntimeError("SEC response exceeds the configured size limit")
        return raw


def extract_filing_text(
    event: SecFilingEvent,
    html: str,
    *,
    maximum_characters: int = 500_000,
    signal_terms: Iterable[str] = _DEFAULT_SIGNAL_TERMS,
) -> ExtractedFilingText:
    if not isinstance(html, str) or not html.strip():
        raise ValueError("filing HTML cannot be empty")
    if not 1_000 <= maximum_characters <= 2_000_000:
        raise ValueError("maximum_characters outside reviewed bounds")

    parser = _VisibleTextParser()
    parser.feed(html)
    parser.close()
    normalized = re.sub(r"\s+", " ", " ".join(parser.parts)).strip()
    if not normalized:
        raise ValueError("filing HTML contains no visible text")
    truncated = len(normalized) > maximum_characters
    text = normalized[:maximum_characters]
    lower = text.casefold()

    item_pattern = re.compile(r"\bitem\s+(\d{1,2}\.\d{2})\b", re.IGNORECASE)
    detected_items = tuple(sorted(set(item_pattern.findall(text))))
    normalized_terms = tuple(
        sorted({term.strip().casefold() for term in signal_terms if term.strip()})
    )
    signals = tuple(term for term in normalized_terms if term in lower)
    payload = {
        "accession_number": event.accession_number,
        "form": event.form,
        "text_sha256": sha256(text.encode("utf-8")).hexdigest(),
        "character_count": len(text),
        "detected_items": detected_items,
        "signal_terms": signals,
        "truncated": truncated,
    }
    return ExtractedFilingText(
        accession_number=event.accession_number,
        form=event.form,
        text=text,
        character_count=len(text),
        detected_items=detected_items,
        signal_terms=signals,
        truncated=truncated,
        fingerprint=_fingerprint(payload),
    )


def extract_xbrl_facts(
    event: SecFilingEvent,
    companyfacts_payload: Mapping[str, Any],
    *,
    maximum_current_facts: int = 500,
) -> XbrlExtraction:
    if not 1 <= maximum_current_facts <= 5_000:
        raise ValueError("maximum_current_facts outside reviewed bounds")
    cik = str(companyfacts_payload.get("cik", "")).strip().lstrip("0") or "0"
    if cik != event.cik:
        raise ValueError("Company Facts CIK does not match the filing event")
    facts_root = companyfacts_payload.get("facts")
    if not isinstance(facts_root, Mapping):
        raise ValueError("Company Facts payload is missing facts")

    all_facts: list[XbrlFact] = []
    for taxonomy, concepts in facts_root.items():
        if not isinstance(taxonomy, str) or not isinstance(concepts, Mapping):
            continue
        for concept, concept_payload in concepts.items():
            if not isinstance(concept, str) or not isinstance(concept_payload, Mapping):
                continue
            units = concept_payload.get("units")
            if not isinstance(units, Mapping):
                continue
            for unit, records in units.items():
                if not isinstance(unit, str) or not isinstance(records, list):
                    continue
                for record in records:
                    fact = _normalize_fact(taxonomy, concept, unit, record)
                    if fact is not None:
                        all_facts.append(fact)

    current = [
        fact
        for fact in all_facts
        if fact.accession_number == event.accession_number and fact.form == event.form
    ]
    current.sort(key=lambda fact: (fact.taxonomy, fact.concept, fact.unit, fact.end, fact.value))
    if len(current) > maximum_current_facts:
        raise RuntimeError("current filing facts exceed the configured limit")

    comparisons: list[FactComparison] = []
    history_by_key: dict[tuple[str, str, str], list[XbrlFact]] = {}
    for fact in all_facts:
        history_by_key.setdefault((fact.taxonomy, fact.concept, fact.unit), []).append(fact)
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
        previous = max(candidates, key=lambda item: (item.end, item.filed, item.accession_number))
        comparisons.append(_compare_facts(fact, previous))

    comparisons.sort(key=lambda item: (item.taxonomy, item.concept, item.unit))
    eligible = bool(current)
    reason = None if eligible else "NO_MATCHING_XBRL_FACTS"
    payload = {
        "cik": cik,
        "accession_number": event.accession_number,
        "current": [asdict(fact) for fact in current],
        "comparisons": [asdict(item) for item in comparisons],
        "eligible": eligible,
        "ineligible_reason": reason,
    }
    return XbrlExtraction(
        cik=cik,
        accession_number=event.accession_number,
        current_facts=tuple(current),
        comparisons=tuple(comparisons),
        eligible=eligible,
        ineligible_reason=reason,
        fingerprint=_fingerprint(payload),
    )


def score_filing_materiality(
    event: SecFilingEvent,
    text: ExtractedFilingText,
    xbrl: XbrlExtraction,
) -> MaterialityAssessment:
    if text.accession_number != event.accession_number or xbrl.accession_number != event.accession_number:
        raise ValueError("filing evidence accession numbers must match")

    score = _FORM_WEIGHTS.get(event.form, 5)
    reasons = [f"form:{event.form}:+{score}"]

    item_score = 0
    for item in sorted(set(event.items) | set(text.detected_items)):
        weight = _ITEM_WEIGHTS.get(item, 0)
        if weight:
            item_score += weight
            reasons.append(f"item:{item}:+{weight}")
    score += min(item_score, 30)

    signal_score = 0
    for term in text.signal_terms:
        weight = _SIGNAL_WEIGHTS.get(term, 0)
        if weight:
            signal_score += weight
            reasons.append(f"signal:{term}:+{weight}")
    score += min(signal_score, 36)

    fact_score = 0
    material_comparisons = [
        item
        for item in xbrl.comparisons
        if any(hint in item.concept.casefold() for hint in _MATERIAL_CONCEPT_HINTS)
    ]
    for comparison in material_comparisons:
        contribution = 0
        ratio = comparison.change_ratio
        if comparison.sign_reversal:
            contribution = max(contribution, 10)
        if ratio is not None:
            magnitude = abs(ratio)
            if magnitude >= 0.50:
                contribution = max(contribution, 12)
            elif magnitude >= 0.25:
                contribution = max(contribution, 8)
            elif magnitude >= 0.10:
                contribution = max(contribution, 4)
        if contribution:
            fact_score += contribution
            reasons.append(f"xbrl:{comparison.concept}:+{contribution}")
    score += min(fact_score, 28)

    evidence_sufficient = text.character_count >= 100 or bool(xbrl.current_facts)
    if not evidence_sufficient:
        reasons.append("insufficient_evidence")
        score = min(score, 19)
    score = max(0, min(int(score), 100))
    if score >= 75:
        level = MaterialityLevel.CRITICAL
    elif score >= 50:
        level = MaterialityLevel.HIGH
    elif score >= 25:
        level = MaterialityLevel.MODERATE
    else:
        level = MaterialityLevel.LOW

    payload = {
        "accession_number": event.accession_number,
        "score": score,
        "level": level.value,
        "reasons": reasons,
        "evidence_sufficient": evidence_sufficient,
        "text_fingerprint": text.fingerprint,
        "xbrl_fingerprint": xbrl.fingerprint,
    }
    return MaterialityAssessment(
        score=score,
        level=level,
        reasons=tuple(reasons),
        evidence_sufficient=evidence_sufficient,
        fingerprint=_fingerprint(payload),
    )


def evaluate_historical_outcomes(
    event: SecFilingEvent,
    prices: Sequence[PriceObservation],
    *,
    horizons: Sequence[int] = (1, 5, 20),
    benchmark_prices: Sequence[PriceObservation] | None = None,
) -> HistoricalOutcomeReport:
    normalized_horizons = tuple(sorted(set(horizons)))
    if not normalized_horizons or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 252
        for value in normalized_horizons
    ):
        raise ValueError("horizons must contain unique integers in [1, 252]")

    ordered = _validate_prices(prices)
    event_at = datetime.fromisoformat(event.filed_at_utc).astimezone(UTC)
    baseline_index = next(
        (index for index, item in enumerate(ordered) if _price_time(item) >= event_at),
        None,
    )
    if baseline_index is None:
        return _empty_outcome(event, event_at, "NO_PRICE_AT_OR_AFTER_FILING")
    if baseline_index + max(normalized_horizons) >= len(ordered):
        return _empty_outcome(event, event_at, "INSUFFICIENT_FORWARD_PRICES")

    benchmark_by_time: dict[str, PriceObservation] | None = None
    if benchmark_prices is not None:
        benchmark = _validate_prices(benchmark_prices)
        benchmark_by_time = {item.observed_at_utc: item for item in benchmark}

    baseline = ordered[baseline_index]
    outcomes: list[OutcomePoint] = []
    for horizon in normalized_horizons:
        outcome = ordered[baseline_index + horizon]
        raw_return = outcome.close / baseline.close - 1.0
        benchmark_return: float | None = None
        abnormal_return: float | None = None
        if benchmark_by_time is not None:
            benchmark_start = benchmark_by_time.get(baseline.observed_at_utc)
            benchmark_end = benchmark_by_time.get(outcome.observed_at_utc)
            if benchmark_start is None or benchmark_end is None:
                return _empty_outcome(event, event_at, "BENCHMARK_TIMESTAMPS_DO_NOT_ALIGN")
            benchmark_return = benchmark_end.close / benchmark_start.close - 1.0
            abnormal_return = raw_return - benchmark_return
        outcomes.append(
            OutcomePoint(
                horizon=horizon,
                baseline_at_utc=baseline.observed_at_utc,
                outcome_at_utc=outcome.observed_at_utc,
                raw_return=raw_return,
                benchmark_return=benchmark_return,
                abnormal_return=abnormal_return,
            )
        )

    payload = {
        "accession_number": event.accession_number,
        "event_at_utc": event_at.replace(microsecond=0).isoformat(),
        "outcomes": [asdict(item) for item in outcomes],
        "eligible": True,
        "ineligible_reason": None,
    }
    return HistoricalOutcomeReport(
        accession_number=event.accession_number,
        event_at_utc=payload["event_at_utc"],
        outcomes=tuple(outcomes),
        eligible=True,
        ineligible_reason=None,
        fingerprint=_fingerprint(payload),
    )


def build_filing_analysis_report(
    event: SecFilingEvent,
    *,
    filing_html: str,
    companyfacts_payload: Mapping[str, Any],
    prices: Sequence[PriceObservation] | None = None,
    benchmark_prices: Sequence[PriceObservation] | None = None,
    horizons: Sequence[int] = (1, 5, 20),
) -> FilingAnalysisReport:
    text = extract_filing_text(event, filing_html)
    xbrl = extract_xbrl_facts(event, companyfacts_payload)
    materiality = score_filing_materiality(event, text, xbrl)
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
        "xbrl_fingerprint": xbrl.fingerprint,
        "materiality_fingerprint": materiality.fingerprint,
        "outcome_fingerprint": outcomes.fingerprint if outcomes else None,
        "paper_only": True,
        "grants_execution_authority": False,
    }
    return FilingAnalysisReport(
        event_fingerprint=event.fingerprint,
        text=text,
        xbrl=xbrl,
        materiality=materiality,
        outcomes=outcomes,
        fingerprint=_fingerprint(payload),
    )


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
        (current_value < 0 < previous_value)
        or (previous_value < 0 < current_value)
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


def _validate_prices(prices: Sequence[PriceObservation]) -> tuple[PriceObservation, ...]:
    if not prices:
        raise ValueError("prices cannot be empty")
    ordered = tuple(sorted(prices, key=_price_time))
    timestamps = [item.observed_at_utc for item in ordered]
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("price timestamps must be unique")
    return ordered


def _price_time(item: PriceObservation) -> datetime:
    return datetime.fromisoformat(item.observed_at_utc).astimezone(UTC)


def _empty_outcome(
    event: SecFilingEvent,
    event_at: datetime,
    reason: str,
) -> HistoricalOutcomeReport:
    payload = {
        "accession_number": event.accession_number,
        "event_at_utc": event_at.replace(microsecond=0).isoformat(),
        "outcomes": [],
        "eligible": False,
        "ineligible_reason": reason,
    }
    return HistoricalOutcomeReport(
        accession_number=event.accession_number,
        event_at_utc=payload["event_at_utc"],
        outcomes=(),
        eligible=False,
        ineligible_reason=reason,
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
    "ExtractedFilingText",
    "FactComparison",
    "FilingAnalysisReport",
    "HistoricalOutcomeReport",
    "MaterialityAssessment",
    "MaterialityLevel",
    "OutcomePoint",
    "PriceObservation",
    "SecFilingContentClient",
    "XbrlExtraction",
    "XbrlFact",
    "build_filing_analysis_report",
    "evaluate_historical_outcomes",
    "extract_filing_text",
    "extract_xbrl_facts",
    "score_filing_materiality",
]
