"""One versioned feature contract for training and US PAPER inference."""
from __future__ import annotations

from datetime import datetime
import math

from aipro.intelligence.market_features import MarketFeaturePolicy, build_market_feature_snapshot
from aipro.us_stocks.portfolio_market import Quote, instant

FEATURE_NAMES = (
    "return_short_pct", "return_medium_pct", "realized_volatility_pct",
    "average_true_range_pct", "volume_ratio", "log_quote_volume_average",
    "trend_score", "log_illiquidity_score",
)
FEATURE_SCHEMA = "us-short-market-v1"


def model_features(quote: Quote, as_of_utc: datetime) -> tuple[tuple[float, ...], str]:
    now = instant(as_of_utc)
    if any(instant(bar.timestamp_utc) >= now for bar in quote.intraday_bars):
        raise ValueError("model features require completed observable bars")
    snapshot = build_market_feature_snapshot(quote.symbol, quote.intraday_bars,
        as_of_utc=now, policy=MarketFeaturePolicy(maximum_age_seconds=120))
    if not snapshot.eligible:
        raise ValueError("model feature history is ineligible")
    values = (snapshot.return_short_pct, snapshot.return_medium_pct,
              snapshot.realized_volatility_pct, snapshot.average_true_range_pct,
              snapshot.volume_ratio, math.log1p(snapshot.quote_volume_average),
              snapshot.trend_score, math.log1p(snapshot.illiquidity_score))
    if any(not math.isfinite(value) for value in values):
        raise ValueError("non-finite model feature")
    return values, snapshot.fingerprint
