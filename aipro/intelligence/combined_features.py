from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping

from aipro.intelligence.features import PaperIntelligenceSnapshot
from aipro.intelligence.macro import MacroRegime, MacroSnapshot
from aipro.intelligence.market_features import MarketFeatureSnapshot
from aipro.intelligence.sec_edgar import FilingEventType, FilingSnapshot

SCHEMA_VERSION = "paper-feature-vector-v1"
FEATURE_NAMES = (
    "news_fused_sentiment",
    "news_confidence",
    "news_native_sentiment",
    "news_native_relevance",
    "news_article_count",
    "news_positive_ratio",
    "news_negative_ratio",
    "macro_score",
    "macro_risk_on",
    "macro_risk_off",
    "filing_event_count",
    "filing_material_event_count",
    "filing_offering_count",
    "filing_insider_count",
    "market_return_short_pct",
    "market_return_medium_pct",
    "market_realized_volatility_pct",
    "market_atr_pct",
    "market_volume_ratio",
    "market_spread_bps",
    "market_illiquidity_score",
    "market_trend_score",
)


@dataclass(frozen=True, slots=True)
class CombinedFeaturePolicy:
    maximum_component_skew_seconds: float = 300.0
    require_news: bool = True
    require_macro: bool = True
    require_filings: bool = True
    require_market: bool = True

    def __post_init__(self) -> None:
        if self.maximum_component_skew_seconds < 0:
            raise ValueError("maximum_component_skew_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class CombinedPaperFeatureVector:
    schema_version: str
    symbol: str
    as_of_utc: str
    feature_names: tuple[str, ...]
    values: tuple[float, ...]
    source_fingerprints: tuple[tuple[str, str], ...]
    eligible: bool
    ineligible_reasons: tuple[str, ...]
    fingerprint: str

    def as_mapping(self) -> Mapping[str, float]:
        return dict(zip(self.feature_names, self.values, strict=True))


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        raise ValueError("component timestamps must be timezone-aware")
    return parsed.astimezone(UTC)


def build_combined_paper_feature_vector(
    *,
    symbol: str,
    as_of_utc: datetime,
    news: PaperIntelligenceSnapshot,
    macro: MacroSnapshot,
    filings: FilingSnapshot,
    market: MarketFeatureSnapshot,
    policy: CombinedFeaturePolicy | None = None,
) -> CombinedPaperFeatureVector:
    active = policy or CombinedFeaturePolicy()
    if as_of_utc.tzinfo is None:
        raise ValueError("as_of_utc must be timezone-aware")
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required")
    if news.symbol != normalized_symbol or market.symbol != normalized_symbol:
        raise ValueError("component symbol mismatch")

    components = {
        "news": news,
        "macro": macro,
        "filings": filings,
        "market": market,
    }
    reasons: list[str] = []
    requirements = {
        "news": active.require_news,
        "macro": active.require_macro,
        "filings": active.require_filings,
        "market": active.require_market,
    }
    for name, component in components.items():
        if requirements[name] and not component.eligible:
            reason = getattr(component, "ineligible_reason", None)
            if reason is None:
                nested = getattr(component, "ineligible_reasons", ())
                reason = ",".join(nested) if nested else "INELIGIBLE"
            reasons.append(f"{name.upper()}:{reason}")

    component_times = [_parse_utc(component.as_of_utc) for component in components.values()]
    now = as_of_utc.astimezone(UTC)
    if any(timestamp > now for timestamp in component_times):
        reasons.append("FUTURE_COMPONENT_TIMESTAMP")
    if component_times:
        skew = (max(component_times) - min(component_times)).total_seconds()
        if skew > active.maximum_component_skew_seconds:
            reasons.append("COMPONENT_TIME_SKEW")

    article_count = max(news.article_count, 1)
    filing_counts = {event_type.value: 0 for event_type in FilingEventType}
    for event in filings.events:
        filing_counts[event.event_type.value] += 1

    values = (
        news.fused_sentiment_score,
        news.fused_sentiment_confidence,
        news.native_sentiment_score,
        news.native_relevance,
        float(news.article_count),
        news.positive_count / article_count,
        news.negative_count / article_count,
        macro.score,
        1.0 if macro.regime == MacroRegime.RISK_ON else 0.0,
        1.0 if macro.regime == MacroRegime.RISK_OFF else 0.0,
        float(len(filings.events)),
        float(filing_counts[FilingEventType.MATERIAL_EVENT.value]),
        float(filing_counts[FilingEventType.SECURITIES_OFFERING.value]),
        float(filing_counts[FilingEventType.INSIDER_TRANSACTION.value]),
        market.return_short_pct,
        market.return_medium_pct,
        market.realized_volatility_pct,
        market.average_true_range_pct,
        market.volume_ratio,
        market.spread_bps_average or 0.0,
        market.illiquidity_score,
        market.trend_score,
    )
    rounded = tuple(round(float(value), 8) for value in values)
    source_fingerprints = tuple(sorted((name, component.fingerprint) for name, component in components.items()))
    canonical = {
        "schema_version": SCHEMA_VERSION,
        "symbol": normalized_symbol,
        "as_of_utc": now.replace(microsecond=0).isoformat(),
        "feature_names": FEATURE_NAMES,
        "values": rounded,
        "source_fingerprints": source_fingerprints,
        "eligible": not reasons,
        "ineligible_reasons": sorted(set(reasons)),
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return CombinedPaperFeatureVector(
        schema_version=SCHEMA_VERSION,
        symbol=normalized_symbol,
        as_of_utc=canonical["as_of_utc"],
        feature_names=FEATURE_NAMES,
        values=rounded,
        source_fingerprints=source_fingerprints,
        eligible=canonical["eligible"],
        ineligible_reasons=tuple(canonical["ineligible_reasons"]),
        fingerprint=fingerprint,
    )


__all__ = [
    "CombinedFeaturePolicy",
    "CombinedPaperFeatureVector",
    "FEATURE_NAMES",
    "SCHEMA_VERSION",
    "build_combined_paper_feature_vector",
]
