from datetime import UTC, datetime, timedelta

from aipro.intelligence.features import (
    EventCategory,
    NativeTickerSentiment,
    build_paper_intelligence_snapshot,
    classify_event,
)
from aipro.intelligence.news import NewsArticle, SentimentObservation
from aipro.intelligence.providers import AlphaVantageSentimentProvider


class FakeHttp:
    def get_json(self, url: str, params: dict[str, str]) -> object:
        return {
            "feed": [
                {
                    "title": "Bitcoin product launch drives growth",
                    "summary": "A major network product release beat expectations.",
                    "url": "https://example.com/a",
                    "source": "Example",
                    "time_published": "20260719T060000",
                    "ticker_sentiment": [
                        {
                            "ticker": "BTC",
                            "relevance_score": "0.9",
                            "ticker_sentiment_score": "0.7",
                            "ticker_sentiment_label": "Bullish",
                        }
                    ],
                }
            ]
        }


def test_alpha_vantage_preserves_native_ticker_sentiment() -> None:
    provider = AlphaVantageSentimentProvider("key", http=FakeHttp())  # type: ignore[arg-type]
    articles, native = provider.fetch_native_sentiment(
        ["BTC"], since_utc=datetime(2026, 7, 19, 5, tzinfo=UTC)
    )

    assert len(articles) == 1
    assert len(native) == 1
    assert native[0].symbol == "BTC"
    assert native[0].relevance_score == 0.9
    assert native[0].sentiment_score == 0.7
    assert native[0].sentiment_label == "bullish"
    assert native[0].article_fingerprint == articles[0].fingerprint


def test_event_classification_is_deterministic() -> None:
    article = NewsArticle(
        provider="test",
        provider_id="1",
        headline="Company launches new product",
        summary="The release expands its network.",
        url="https://example.com/1",
        source="Example",
        published_at_utc="2026-07-19T06:00:00+00:00",
        symbols=("BTC",),
    )
    assert classify_event(article) is EventCategory.PRODUCT
    assert classify_event(article) is EventCategory.PRODUCT


def test_paper_snapshot_is_deterministic_and_freshness_gated() -> None:
    as_of = datetime(2026, 7, 19, 6, 30, tzinfo=UTC)
    article = NewsArticle(
        provider="test",
        provider_id="1",
        headline="Bitcoin earnings growth beats forecast",
        summary="Quarterly profit improved.",
        url="https://example.com/1",
        source="Example",
        published_at_utc="2026-07-19T06:00:00+00:00",
        symbols=("BTC",),
    )
    observation = SentimentObservation(
        provider="test",
        article_fingerprint=article.fingerprint,
        score=0.6,
        confidence=0.8,
    )
    native = NativeTickerSentiment(
        provider="alpha_vantage",
        article_fingerprint=article.fingerprint,
        symbol="BTC",
        relevance_score=0.9,
        sentiment_score=0.7,
        sentiment_label="bullish",
    )

    first = build_paper_intelligence_snapshot(
        "BTC", [article], [observation], [native], as_of_utc=as_of
    )
    second = build_paper_intelligence_snapshot(
        "BTC", [article], [observation], [native], as_of_utc=as_of
    )

    assert first == second
    assert first.eligible is True
    assert first.fingerprint == second.fingerprint
    assert first.native_sentiment_score == 0.7
    assert dict(first.event_counts)["earnings"] == 1

    stale = build_paper_intelligence_snapshot(
        "BTC",
        [article],
        [observation],
        [native],
        as_of_utc=as_of + timedelta(hours=2),
        max_article_age_sec=3600,
    )
    assert stale.eligible is False
    assert stale.ineligible_reason == "STALE_INTELLIGENCE"


def test_snapshot_fails_closed_without_relevant_articles() -> None:
    snapshot = build_paper_intelligence_snapshot(
        "ETH", [], [], [], as_of_utc=datetime(2026, 7, 19, 6, tzinfo=UTC)
    )
    assert snapshot.eligible is False
    assert snapshot.ineligible_reason == "NO_RELEVANT_ARTICLES"
