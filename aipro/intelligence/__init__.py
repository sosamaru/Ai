"""Asset-neutral intelligence components for AiPro."""

from aipro.intelligence.news import (
    NewsArticle,
    NewsBatch,
    NewsPipeline,
    NewsProvider,
    SentimentObservation,
    deduplicate_articles,
)

__all__ = [
    "NewsArticle",
    "NewsBatch",
    "NewsPipeline",
    "NewsProvider",
    "SentimentObservation",
    "deduplicate_articles",
]
