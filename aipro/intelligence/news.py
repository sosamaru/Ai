from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol, Sequence
from urllib.parse import urlsplit, urlunsplit

_TOKEN_RE = re.compile(r"[A-Za-z0-9가-힣]+")


@dataclass(frozen=True, slots=True)
class NewsArticle:
    provider: str
    provider_id: str
    headline: str
    summary: str
    url: str
    source: str
    published_at_utc: str
    symbols: tuple[str, ...] = ()
    category: str = "general"

    def __post_init__(self) -> None:
        if not self.provider.strip() or not self.provider_id.strip():
            raise ValueError("provider and provider_id are required")
        if not self.headline.strip():
            raise ValueError("headline is required")
        published = datetime.fromisoformat(self.published_at_utc)
        if published.tzinfo is None:
            raise ValueError("published_at_utc must be timezone-aware")
        normalized_symbols = tuple(sorted({item.strip().upper() for item in self.symbols if item.strip()}))
        object.__setattr__(self, "symbols", normalized_symbols)

    @property
    def canonical_url(self) -> str:
        parts = urlsplit(self.url.strip())
        return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))

    @property
    def fingerprint(self) -> str:
        canonical = {
            "headline": _normalize_text(self.headline),
            "published_minute": datetime.fromisoformat(self.published_at_utc)
            .astimezone(UTC)
            .replace(second=0, microsecond=0)
            .isoformat(),
            "source": self.source.strip().lower(),
            "url": self.canonical_url,
        }
        payload = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SentimentObservation:
    provider: str
    article_fingerprint: str
    score: float
    confidence: float

    def __post_init__(self) -> None:
        if not -1.0 <= self.score <= 1.0:
            raise ValueError("sentiment score must be between -1 and 1")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("sentiment confidence must be between 0 and 1")
        if len(self.article_fingerprint) != 64:
            raise ValueError("article_fingerprint must be a SHA-256 digest")


@dataclass(frozen=True, slots=True)
class NewsBatch:
    articles: tuple[NewsArticle, ...]
    fetched_at_utc: str
    provider_health: dict[str, bool]

    def __post_init__(self) -> None:
        fetched = datetime.fromisoformat(self.fetched_at_utc)
        if fetched.tzinfo is None:
            raise ValueError("fetched_at_utc must be timezone-aware")


class NewsProvider(Protocol):
    name: str

    def fetch(self, symbols: Sequence[str], *, since_utc: datetime) -> Sequence[NewsArticle]: ...


class SentimentProvider(Protocol):
    name: str

    def score(self, articles: Sequence[NewsArticle]) -> Sequence[SentimentObservation]: ...


def _normalize_text(value: str) -> str:
    return " ".join(_TOKEN_RE.findall(value.lower()))


def headline_similarity(left: str, right: str) -> float:
    left_tokens = set(_TOKEN_RE.findall(left.lower()))
    right_tokens = set(_TOKEN_RE.findall(right.lower()))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def deduplicate_articles(
    articles: Sequence[NewsArticle],
    *,
    headline_similarity_threshold: float = 0.82,
) -> tuple[NewsArticle, ...]:
    if not 0.0 <= headline_similarity_threshold <= 1.0:
        raise ValueError("headline_similarity_threshold must be between 0 and 1")
    ordered = sorted(
        articles,
        key=lambda item: datetime.fromisoformat(item.published_at_utc).astimezone(UTC),
        reverse=True,
    )
    kept: list[NewsArticle] = []
    fingerprints: set[str] = set()
    canonical_urls: set[str] = set()
    for article in ordered:
        if article.fingerprint in fingerprints:
            continue
        if article.canonical_url and article.canonical_url in canonical_urls:
            continue
        duplicate = any(
            item.source.strip().lower() == article.source.strip().lower()
            and headline_similarity(item.headline, article.headline) >= headline_similarity_threshold
            for item in kept
        )
        if duplicate:
            continue
        kept.append(article)
        fingerprints.add(article.fingerprint)
        if article.canonical_url:
            canonical_urls.add(article.canonical_url)
    return tuple(kept)


def symbol_relevance(article: NewsArticle, symbol: str, aliases: Sequence[str] = ()) -> float:
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required")
    if normalized_symbol in article.symbols:
        return 1.0
    searchable = f"{article.headline} {article.summary}".lower()
    terms = {normalized_symbol.lower(), *(alias.strip().lower() for alias in aliases if alias.strip())}
    matches = sum(1 for term in terms if term and re.search(rf"\b{re.escape(term)}\b", searchable))
    return min(1.0, matches / max(1, len(terms)))


def fuse_sentiment(observations: Sequence[SentimentObservation]) -> tuple[float, float]:
    if not observations:
        return 0.0, 0.0
    total_weight = sum(item.confidence for item in observations)
    if total_weight <= 0:
        return 0.0, 0.0
    score = sum(item.score * item.confidence for item in observations) / total_weight
    confidence = 1.0 - math.prod(1.0 - item.confidence for item in observations)
    return max(-1.0, min(1.0, score)), max(0.0, min(1.0, confidence))


class NewsPipeline:
    def __init__(
        self,
        providers: Sequence[NewsProvider],
        *,
        headline_similarity_threshold: float = 0.82,
    ) -> None:
        if not providers:
            raise ValueError("at least one news provider is required")
        names = [provider.name.strip().lower() for provider in providers]
        if any(not name for name in names) or len(set(names)) != len(names):
            raise ValueError("provider names must be non-empty and unique")
        self.providers = tuple(providers)
        self.headline_similarity_threshold = headline_similarity_threshold

    def collect(self, symbols: Sequence[str], *, since_utc: datetime) -> NewsBatch:
        if since_utc.tzinfo is None:
            raise ValueError("since_utc must be timezone-aware")
        normalized_symbols = tuple(sorted({item.strip().upper() for item in symbols if item.strip()}))
        if not normalized_symbols:
            raise ValueError("at least one symbol is required")
        health: dict[str, bool] = {}
        collected: list[NewsArticle] = []
        for provider in self.providers:
            try:
                articles = provider.fetch(normalized_symbols, since_utc=since_utc.astimezone(UTC))
            except Exception:
                health[provider.name] = False
                continue
            health[provider.name] = True
            for article in articles:
                if article.provider.strip().lower() != provider.name.strip().lower():
                    raise ValueError("provider returned article with mismatched provider name")
                collected.append(article)
        return NewsBatch(
            articles=deduplicate_articles(
                collected,
                headline_similarity_threshold=self.headline_similarity_threshold,
            ),
            fetched_at_utc=datetime.now(UTC).isoformat(),
            provider_health=health,
        )


__all__ = [
    "NewsArticle",
    "NewsBatch",
    "NewsPipeline",
    "NewsProvider",
    "SentimentObservation",
    "SentimentProvider",
    "deduplicate_articles",
    "fuse_sentiment",
    "headline_similarity",
    "symbol_relevance",
]
