from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, Sequence
from urllib import parse, request

from aipro.intelligence.news import NewsArticle, SentimentObservation


class JsonHttpClient:
    def __init__(self, timeout_sec: float = 10.0) -> None:
        if timeout_sec <= 0:
            raise ValueError("timeout_sec must be positive")
        self.timeout_sec = timeout_sec

    def get_json(self, url: str, params: dict[str, str]) -> Any:
        query = parse.urlencode(params)
        with request.urlopen(f"{url}?{query}", timeout=self.timeout_sec) as response:
            return json.loads(response.read().decode("utf-8"))


class FinnhubNewsProvider:
    name = "finnhub"

    def __init__(self, api_key: str, *, http: JsonHttpClient | None = None) -> None:
        if not api_key.strip():
            raise ValueError("Finnhub API key is required")
        self.api_key = api_key.strip()
        self.http = http or JsonHttpClient()

    def fetch(self, symbols: Sequence[str], *, since_utc: datetime) -> Sequence[NewsArticle]:
        if since_utc.tzinfo is None:
            raise ValueError("since_utc must be timezone-aware")
        start_date = since_utc.astimezone(UTC).date().isoformat()
        end_date = datetime.now(UTC).date().isoformat()
        articles: list[NewsArticle] = []
        seen_ids: set[str] = set()
        for symbol in symbols:
            payload = self.http.get_json(
                "https://finnhub.io/api/v1/company-news",
                {
                    "symbol": symbol,
                    "from": start_date,
                    "to": end_date,
                    "token": self.api_key,
                },
            )
            if not isinstance(payload, list):
                raise RuntimeError("Finnhub returned a non-list response")
            for item in payload:
                if not isinstance(item, dict):
                    continue
                provider_id = str(item.get("id", "")).strip()
                headline = str(item.get("headline", "")).strip()
                timestamp = item.get("datetime")
                if not provider_id or not headline or not isinstance(timestamp, (int, float)):
                    continue
                if provider_id in seen_ids:
                    continue
                seen_ids.add(provider_id)
                articles.append(
                    NewsArticle(
                        provider=self.name,
                        provider_id=provider_id,
                        headline=headline,
                        summary=str(item.get("summary", "")).strip(),
                        url=str(item.get("url", "")).strip(),
                        source=str(item.get("source", "Finnhub")).strip() or "Finnhub",
                        published_at_utc=datetime.fromtimestamp(timestamp, tz=UTC).isoformat(),
                        symbols=(symbol,),
                        category=str(item.get("category", "company")).strip() or "company",
                    )
                )
        return tuple(articles)


class AlphaVantageSentimentProvider:
    name = "alpha_vantage"

    def __init__(self, api_key: str, *, http: JsonHttpClient | None = None) -> None:
        if not api_key.strip():
            raise ValueError("Alpha Vantage API key is required")
        self.api_key = api_key.strip()
        self.http = http or JsonHttpClient()

    def fetch_sentiment(
        self,
        symbols: Sequence[str],
        *,
        since_utc: datetime,
        limit: int = 50,
    ) -> tuple[NewsArticle, ...]:
        if since_utc.tzinfo is None:
            raise ValueError("since_utc must be timezone-aware")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        payload = self.http.get_json(
            "https://www.alphavantage.co/query",
            {
                "function": "NEWS_SENTIMENT",
                "tickers": ",".join(symbols),
                "time_from": since_utc.astimezone(UTC).strftime("%Y%m%dT%H%M"),
                "limit": str(limit),
                "apikey": self.api_key,
            },
        )
        if not isinstance(payload, dict):
            raise RuntimeError("Alpha Vantage returned a non-object response")
        feed = payload.get("feed", [])
        if not isinstance(feed, list):
            raise RuntimeError("Alpha Vantage feed is invalid")
        articles: list[NewsArticle] = []
        for index, item in enumerate(feed):
            if not isinstance(item, dict):
                continue
            headline = str(item.get("title", "")).strip()
            published_raw = str(item.get("time_published", "")).strip()
            if not headline or not published_raw:
                continue
            published = datetime.strptime(published_raw, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
            ticker_sentiment = item.get("ticker_sentiment", [])
            article_symbols = tuple(
                str(entry.get("ticker", "")).strip().upper()
                for entry in ticker_sentiment
                if isinstance(entry, dict) and str(entry.get("ticker", "")).strip()
            )
            provider_id = str(item.get("url", "")).strip() or f"alpha-{published_raw}-{index}"
            articles.append(
                NewsArticle(
                    provider=self.name,
                    provider_id=provider_id,
                    headline=headline,
                    summary=str(item.get("summary", "")).strip(),
                    url=str(item.get("url", "")).strip(),
                    source=str(item.get("source", "Alpha Vantage")).strip() or "Alpha Vantage",
                    published_at_utc=published.isoformat(),
                    symbols=article_symbols,
                    category="sentiment",
                )
            )
        return tuple(articles)

    def score(self, articles: Sequence[NewsArticle]) -> Sequence[SentimentObservation]:
        observations: list[SentimentObservation] = []
        for article in articles:
            text = f"{article.headline} {article.summary}".lower()
            positive = sum(text.count(word) for word in ("beat", "growth", "surge", "upgrade", "profit"))
            negative = sum(text.count(word) for word in ("miss", "drop", "downgrade", "loss", "lawsuit"))
            total = positive + negative
            score = 0.0 if total == 0 else (positive - negative) / total
            confidence = min(0.8, 0.2 + total * 0.1) if total else 0.1
            observations.append(
                SentimentObservation(
                    provider=self.name,
                    article_fingerprint=article.fingerprint,
                    score=score,
                    confidence=confidence,
                )
            )
        return tuple(observations)


__all__ = ["AlphaVantageSentimentProvider", "FinnhubNewsProvider", "JsonHttpClient"]
