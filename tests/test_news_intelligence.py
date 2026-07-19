from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aipro.intelligence.news import (
    NewsArticle,
    NewsPipeline,
    SentimentObservation,
    deduplicate_articles,
    fuse_sentiment,
    symbol_relevance,
)
from aipro.intelligence.providers import AlphaVantageSentimentProvider, FinnhubNewsProvider


def article(**overrides: object) -> NewsArticle:
    values: dict[str, object] = {
        "provider": "finnhub",
        "provider_id": "1",
        "headline": "Apple reports strong quarterly growth",
        "summary": "Apple revenue beat expectations.",
        "url": "https://example.com/story?tracking=1",
        "source": "Example",
        "published_at_utc": "2026-07-19T01:00:00+00:00",
        "symbols": ("AAPL",),
        "category": "company",
    }
    values.update(overrides)
    return NewsArticle(**values)


def test_article_normalizes_symbols_and_url() -> None:
    item = article(symbols=("aapl", " AAPL "), url="HTTPS://EXAMPLE.COM/story/?x=1")
    assert item.symbols == ("AAPL",)
    assert item.canonical_url == "https://example.com/story"
    assert len(item.fingerprint) == 64


def test_article_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        article(published_at_utc="2026-07-19T01:00:00")


def test_deduplication_removes_tracking_url_and_similar_headline_duplicates() -> None:
    duplicate_url = article(provider_id="2", url="https://example.com/story?other=2")
    similar = article(
        provider_id="3",
        url="https://example.com/another",
        headline="Apple reports strong quarterly growth today",
    )
    unique = article(
        provider_id="4",
        url="https://example.com/unique",
        headline="Federal Reserve leaves interest rates unchanged",
        symbols=(),
    )
    result = deduplicate_articles((duplicate_url, similar, unique, article()))
    assert len(result) == 2
    assert {item.provider_id for item in result} <= {"1", "2", "3", "4"}
    assert any("Federal Reserve" in item.headline for item in result)


def test_symbol_relevance_prefers_explicit_mapping() -> None:
    assert symbol_relevance(article(), "AAPL", aliases=("Apple",)) == 1.0
    unmapped = article(symbols=())
    assert symbol_relevance(unmapped, "AAPL", aliases=("Apple",)) == 0.5


def test_sentiment_fusion_is_confidence_weighted() -> None:
    fingerprint = article().fingerprint
    score, confidence = fuse_sentiment(
        (
            SentimentObservation("one", fingerprint, 1.0, 0.8),
            SentimentObservation("two", fingerprint, -1.0, 0.2),
        )
    )
    assert score == pytest.approx(0.6)
    assert confidence == pytest.approx(0.84)


class GoodProvider:
    name = "good"

    def fetch(self, symbols: tuple[str, ...], *, since_utc: datetime) -> tuple[NewsArticle, ...]:
        return (article(provider="good", symbols=symbols),)


class BrokenProvider:
    name = "broken"

    def fetch(self, symbols: tuple[str, ...], *, since_utc: datetime) -> tuple[NewsArticle, ...]:
        raise RuntimeError("temporary failure")


def test_pipeline_isolates_provider_failure() -> None:
    batch = NewsPipeline((GoodProvider(), BrokenProvider())).collect(
        ("AAPL",), since_utc=datetime(2026, 7, 19, tzinfo=UTC)
    )
    assert len(batch.articles) == 1
    assert batch.provider_health == {"good": True, "broken": False}


def test_pipeline_rejects_naive_since_timestamp() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        NewsPipeline((GoodProvider(),)).collect(("AAPL",), since_utc=datetime(2026, 7, 19))


class FakeFinnhubHttp:
    def get_json(self, url: str, params: dict[str, str]) -> object:
        return [
            {
                "id": 10,
                "headline": "Apple launches product",
                "summary": "New product announced",
                "url": "https://example.com/apple",
                "source": "Wire",
                "datetime": 1784422800,
                "category": "company",
            }
        ]


def test_finnhub_adapter_normalizes_response() -> None:
    provider = FinnhubNewsProvider("secret", http=FakeFinnhubHttp())  # type: ignore[arg-type]
    result = provider.fetch(("AAPL",), since_utc=datetime(2026, 7, 18, tzinfo=UTC))
    assert result[0].provider == "finnhub"
    assert result[0].symbols == ("AAPL",)


class FakeAlphaHttp:
    def get_json(self, url: str, params: dict[str, str]) -> object:
        return {
            "feed": [
                {
                    "title": "Apple profit growth beats estimates",
                    "summary": "Revenue growth and profit beat consensus",
                    "url": "https://example.com/alpha",
                    "source": "Wire",
                    "time_published": "20260719T010000",
                    "ticker_sentiment": [{"ticker": "AAPL"}],
                }
            ]
        }


def test_alpha_vantage_adapter_and_local_fallback_score() -> None:
    provider = AlphaVantageSentimentProvider("secret", http=FakeAlphaHttp())  # type: ignore[arg-type]
    articles = provider.fetch_sentiment(("AAPL",), since_utc=datetime(2026, 7, 18, tzinfo=UTC))
    observations = provider.score(articles)
    assert articles[0].symbols == ("AAPL",)
    assert observations[0].score > 0
    assert observations[0].confidence > 0
