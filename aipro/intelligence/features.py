from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Sequence

from aipro.intelligence.news import NewsArticle, SentimentObservation, fuse_sentiment


class EventCategory(StrEnum):
    EARNINGS = "earnings"
    REGULATORY = "regulatory"
    PRODUCT = "product"
    PARTNERSHIP = "partnership"
    FINANCING = "financing"
    LEGAL = "legal"
    SECURITY = "security"
    MACRO = "macro"
    GENERAL = "general"


_EVENT_PATTERNS: tuple[tuple[EventCategory, tuple[str, ...]], ...] = (
    (EventCategory.EARNINGS, ("earnings", "revenue", "profit", "guidance", "quarter")),
    (EventCategory.REGULATORY, ("sec", "regulator", "approval", "filing", "compliance")),
    (EventCategory.PRODUCT, ("launch", "release", "product", "upgrade", "network")),
    (EventCategory.PARTNERSHIP, ("partnership", "partner", "collaboration", "agreement")),
    (EventCategory.FINANCING, ("funding", "financing", "offering", "debt", "capital")),
    (EventCategory.LEGAL, ("lawsuit", "court", "settlement", "legal", "probe")),
    (EventCategory.SECURITY, ("hack", "breach", "exploit", "security", "outage")),
    (EventCategory.MACRO, ("inflation", "interest rate", "federal reserve", "gdp", "jobs report")),
)


@dataclass(frozen=True, slots=True)
class NativeTickerSentiment:
    provider: str
    article_fingerprint: str
    symbol: str
    relevance_score: float
    sentiment_score: float
    sentiment_label: str

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.symbol.strip():
            raise ValueError("provider and symbol are required")
        if len(self.article_fingerprint) != 64:
            raise ValueError("article_fingerprint must be a SHA-256 digest")
        if not 0.0 <= self.relevance_score <= 1.0:
            raise ValueError("relevance_score must be between 0 and 1")
        if not -1.0 <= self.sentiment_score <= 1.0:
            raise ValueError("sentiment_score must be between -1 and 1")
        object.__setattr__(self, "symbol", self.symbol.strip().upper())
        object.__setattr__(self, "sentiment_label", self.sentiment_label.strip().lower() or "neutral")


@dataclass(frozen=True, slots=True)
class PaperIntelligenceSnapshot:
    symbol: str
    as_of_utc: str
    article_count: int
    positive_count: int
    negative_count: int
    neutral_count: int
    fused_sentiment_score: float
    fused_sentiment_confidence: float
    native_sentiment_score: float
    native_relevance: float
    event_counts: tuple[tuple[str, int], ...]
    freshest_article_at_utc: str | None
    eligible: bool
    ineligible_reason: str | None
    fingerprint: str


def classify_event(article: NewsArticle) -> EventCategory:
    text = re.sub(r"\s+", " ", f"{article.headline} {article.summary} {article.category}".lower())
    for category, terms in _EVENT_PATTERNS:
        if any(term in text for term in terms):
            return category
    return EventCategory.GENERAL


def build_paper_intelligence_snapshot(
    symbol: str,
    articles: Sequence[NewsArticle],
    observations: Sequence[SentimentObservation],
    native_sentiments: Sequence[NativeTickerSentiment],
    *,
    as_of_utc: datetime,
    max_article_age_sec: float = 3600.0,
) -> PaperIntelligenceSnapshot:
    if as_of_utc.tzinfo is None:
        raise ValueError("as_of_utc must be timezone-aware")
    if max_article_age_sec <= 0:
        raise ValueError("max_article_age_sec must be positive")
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required")

    relevant = tuple(
        sorted(
            (article for article in articles if normalized_symbol in article.symbols),
            key=lambda item: item.published_at_utc,
        )
    )
    relevant_fingerprints = {item.fingerprint for item in relevant}
    relevant_observations = tuple(
        item for item in observations if item.article_fingerprint in relevant_fingerprints
    )
    relevant_native = tuple(
        item
        for item in native_sentiments
        if item.symbol == normalized_symbol and item.article_fingerprint in relevant_fingerprints
    )

    fused_score, fused_confidence = fuse_sentiment(relevant_observations)
    native_weight = sum(item.relevance_score for item in relevant_native)
    native_score = (
        sum(item.sentiment_score * item.relevance_score for item in relevant_native) / native_weight
        if native_weight > 0
        else 0.0
    )
    native_relevance = min(1.0, native_weight / max(1, len(relevant_native))) if relevant_native else 0.0

    event_counter: dict[str, int] = {}
    for article in relevant:
        category = classify_event(article).value
        event_counter[category] = event_counter.get(category, 0) + 1

    positive_count = sum(1 for item in relevant_observations if item.score > 0.15)
    negative_count = sum(1 for item in relevant_observations if item.score < -0.15)
    neutral_count = max(0, len(relevant) - positive_count - negative_count)
    freshest = max((datetime.fromisoformat(item.published_at_utc).astimezone(UTC) for item in relevant), default=None)

    eligible = True
    reason: str | None = None
    if not relevant:
        eligible = False
        reason = "NO_RELEVANT_ARTICLES"
    elif freshest is None or (as_of_utc.astimezone(UTC) - freshest).total_seconds() > max_article_age_sec:
        eligible = False
        reason = "STALE_INTELLIGENCE"

    canonical = {
        "symbol": normalized_symbol,
        "as_of_utc": as_of_utc.astimezone(UTC).replace(microsecond=0).isoformat(),
        "article_fingerprints": sorted(relevant_fingerprints),
        "fused_sentiment_score": round(fused_score, 8),
        "fused_sentiment_confidence": round(fused_confidence, 8),
        "native_sentiment_score": round(native_score, 8),
        "native_relevance": round(native_relevance, 8),
        "event_counts": sorted(event_counter.items()),
        "eligible": eligible,
        "ineligible_reason": reason,
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return PaperIntelligenceSnapshot(
        symbol=normalized_symbol,
        as_of_utc=canonical["as_of_utc"],
        article_count=len(relevant),
        positive_count=positive_count,
        negative_count=negative_count,
        neutral_count=neutral_count,
        fused_sentiment_score=round(fused_score, 8),
        fused_sentiment_confidence=round(fused_confidence, 8),
        native_sentiment_score=round(native_score, 8),
        native_relevance=round(native_relevance, 8),
        event_counts=tuple(sorted(event_counter.items())),
        freshest_article_at_utc=freshest.isoformat() if freshest else None,
        eligible=eligible,
        ineligible_reason=reason,
        fingerprint=fingerprint,
    )


__all__ = [
    "EventCategory",
    "NativeTickerSentiment",
    "PaperIntelligenceSnapshot",
    "build_paper_intelligence_snapshot",
    "classify_event",
]
