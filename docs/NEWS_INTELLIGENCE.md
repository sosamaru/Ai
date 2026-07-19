# News Intelligence Foundation

AiPro now has an asset-neutral news layer under `aipro/intelligence/`.

## Components

- `NewsArticle` normalizes provider identity, headline, summary, source, publication time, symbols, category, URL, and deterministic SHA-256 fingerprint.
- `NewsProvider` and `SentimentProvider` protocols keep strategy code independent from vendor APIs.
- `NewsPipeline` collects from multiple providers, isolates provider failures, reports provider health, and deduplicates results.
- `symbol_relevance` scores explicit ticker mappings and configurable aliases.
- `fuse_sentiment` combines multiple sentiment observations using confidence weights.
- `FinnhubNewsProvider` maps company-news responses into normalized articles.
- `AlphaVantageSentimentProvider` maps NEWS_SENTIMENT articles and supplies a deterministic local fallback score for offline operation.

## Safety boundary

News data is intelligence input only. It does not:

- submit, cancel, or modify orders
- enable LIVE mode
- alter balances, positions, baselines, approval state, or exchange evidence
- bypass market-data freshness or supervised PAPER validation

A provider failure is recorded in `NewsBatch.provider_health` and does not silently produce fabricated articles.

## Planned environment variables

```text
FINNHUB_API_KEY=
ALPHA_VANTAGE_API_KEY=
```

Keys are not required for offline tests and must never be committed. Runtime configuration and scheduling will be connected only after provider contracts and evidence storage are stable.

## Next steps

1. Append-only news cache and ingestion evidence
2. Provider rate limiting, retry, and freshness policy
3. Alpha Vantage native per-ticker sentiment mapping
4. FRED macro-regime inputs
5. SEC EDGAR filing-event normalization
6. Strategy-feature integration in PAPER only
