from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import fmean, pstdev
from typing import Sequence


@dataclass(frozen=True, slots=True)
class MarketBar:
    timestamp_utc: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float | None = None
    bid_ask_spread_bps: float | None = None

    def __post_init__(self) -> None:
        timestamp = datetime.fromisoformat(self.timestamp_utc)
        if timestamp.tzinfo is None:
            raise ValueError("timestamp_utc must be timezone-aware")
        values = (self.open, self.high, self.low, self.close, self.volume)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("market bar values must be finite")
        if min(self.open, self.high, self.low, self.close) <= 0:
            raise ValueError("prices must be positive")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close) or self.high < self.low:
            raise ValueError("invalid OHLC relationship")
        if self.volume < 0:
            raise ValueError("volume must be non-negative")
        if self.quote_volume is not None and (not math.isfinite(self.quote_volume) or self.quote_volume < 0):
            raise ValueError("quote_volume must be finite and non-negative")
        if self.bid_ask_spread_bps is not None and (
            not math.isfinite(self.bid_ask_spread_bps) or self.bid_ask_spread_bps < 0
        ):
            raise ValueError("bid_ask_spread_bps must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class MarketFeaturePolicy:
    minimum_bars: int = 30
    short_window: int = 5
    medium_window: int = 20
    maximum_age_seconds: float = 300.0
    maximum_zero_volume_fraction: float = 0.20

    def __post_init__(self) -> None:
        if self.minimum_bars < 20:
            raise ValueError("minimum_bars must be at least 20")
        if not 2 <= self.short_window < self.medium_window <= self.minimum_bars:
            raise ValueError("invalid feature windows")
        if self.maximum_age_seconds <= 0:
            raise ValueError("maximum_age_seconds must be positive")
        if not 0 <= self.maximum_zero_volume_fraction < 1:
            raise ValueError("invalid zero-volume fraction")


@dataclass(frozen=True, slots=True)
class MarketFeatureSnapshot:
    symbol: str
    as_of_utc: str
    bar_count: int
    return_short_pct: float
    return_medium_pct: float
    realized_volatility_pct: float
    average_true_range_pct: float
    volume_ratio: float
    quote_volume_average: float
    spread_bps_average: float | None
    illiquidity_score: float
    trend_score: float
    eligible: bool
    ineligible_reasons: tuple[str, ...]
    fingerprint: str


def _pct_return(start: float, end: float) -> float:
    return (end / start - 1.0) * 100.0


def build_market_feature_snapshot(
    symbol: str,
    bars: Sequence[MarketBar],
    *,
    as_of_utc: datetime,
    policy: MarketFeaturePolicy | None = None,
) -> MarketFeatureSnapshot:
    active = policy or MarketFeaturePolicy()
    if as_of_utc.tzinfo is None:
        raise ValueError("as_of_utc must be timezone-aware")
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise ValueError("symbol is required")

    ordered = tuple(sorted(bars, key=lambda item: datetime.fromisoformat(item.timestamp_utc).astimezone(UTC)))
    timestamps = [datetime.fromisoformat(item.timestamp_utc).astimezone(UTC) for item in ordered]
    if len(set(timestamps)) != len(timestamps):
        raise ValueError("duplicate bar timestamps are not allowed")

    reasons: list[str] = []
    if len(ordered) < active.minimum_bars:
        reasons.append("INSUFFICIENT_BARS")
    if not ordered:
        reasons.append("NO_MARKET_DATA")

    selected = ordered[-active.minimum_bars :] if len(ordered) >= active.minimum_bars else ordered
    if selected:
        latest = datetime.fromisoformat(selected[-1].timestamp_utc).astimezone(UTC)
        age_seconds = (as_of_utc.astimezone(UTC) - latest).total_seconds()
        if age_seconds < 0:
            reasons.append("FUTURE_MARKET_DATA")
        elif age_seconds > active.maximum_age_seconds:
            reasons.append("STALE_MARKET_DATA")
        zero_fraction = sum(item.volume == 0 for item in selected) / len(selected)
        if zero_fraction > active.maximum_zero_volume_fraction:
            reasons.append("EXCESS_ZERO_VOLUME")

    if len(selected) >= active.medium_window:
        closes = [item.close for item in selected]
        log_returns = [math.log(closes[index] / closes[index - 1]) for index in range(1, len(closes))]
        short_start = closes[-active.short_window]
        medium_start = closes[-active.medium_window]
        return_short = _pct_return(short_start, closes[-1])
        return_medium = _pct_return(medium_start, closes[-1])
        realized_volatility = pstdev(log_returns) * math.sqrt(len(log_returns)) * 100.0 if len(log_returns) > 1 else 0.0

        true_ranges: list[float] = []
        for index, bar in enumerate(selected):
            previous_close = selected[index - 1].close if index else bar.open
            true_ranges.append(max(bar.high - bar.low, abs(bar.high - previous_close), abs(bar.low - previous_close)))
        atr_pct = fmean(true_ranges[-active.medium_window :]) / closes[-1] * 100.0

        volumes = [item.volume for item in selected]
        recent_volume = fmean(volumes[-active.short_window :])
        baseline_volume = fmean(volumes[-active.medium_window :])
        volume_ratio = recent_volume / baseline_volume if baseline_volume > 0 else 0.0

        quote_values = [
            item.quote_volume if item.quote_volume is not None else item.close * item.volume for item in selected
        ]
        quote_average = fmean(quote_values[-active.medium_window :])
        spreads = [item.bid_ask_spread_bps for item in selected if item.bid_ask_spread_bps is not None]
        spread_average = fmean(spreads[-active.medium_window :]) if spreads else None

        price_change = abs(closes[-1] / closes[-2] - 1.0) if len(closes) > 1 else 0.0
        illiquidity = price_change / max(quote_values[-1], 1e-12) * 1_000_000_000
        trend_score = max(-1.0, min(1.0, (return_short * 0.4 + return_medium * 0.6) / 10.0))
    else:
        return_short = return_medium = realized_volatility = atr_pct = 0.0
        volume_ratio = quote_average = illiquidity = trend_score = 0.0
        spread_average = None

    canonical = {
        "schema_version": 1,
        "symbol": normalized_symbol,
        "as_of_utc": as_of_utc.astimezone(UTC).replace(microsecond=0).isoformat(),
        "bar_fingerprints": [
            hashlib.sha256(json.dumps(asdict(item), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
            for item in selected
        ],
        "return_short_pct": round(return_short, 8),
        "return_medium_pct": round(return_medium, 8),
        "realized_volatility_pct": round(realized_volatility, 8),
        "average_true_range_pct": round(atr_pct, 8),
        "volume_ratio": round(volume_ratio, 8),
        "quote_volume_average": round(quote_average, 8),
        "spread_bps_average": None if spread_average is None else round(spread_average, 8),
        "illiquidity_score": round(illiquidity, 8),
        "trend_score": round(trend_score, 8),
        "eligible": not reasons,
        "ineligible_reasons": sorted(set(reasons)),
    }
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return MarketFeatureSnapshot(
        symbol=normalized_symbol,
        as_of_utc=canonical["as_of_utc"],
        bar_count=len(selected),
        return_short_pct=canonical["return_short_pct"],
        return_medium_pct=canonical["return_medium_pct"],
        realized_volatility_pct=canonical["realized_volatility_pct"],
        average_true_range_pct=canonical["average_true_range_pct"],
        volume_ratio=canonical["volume_ratio"],
        quote_volume_average=canonical["quote_volume_average"],
        spread_bps_average=canonical["spread_bps_average"],
        illiquidity_score=canonical["illiquidity_score"],
        trend_score=canonical["trend_score"],
        eligible=canonical["eligible"],
        ineligible_reasons=tuple(canonical["ineligible_reasons"]),
        fingerprint=fingerprint,
    )


__all__ = ["MarketBar", "MarketFeaturePolicy", "MarketFeatureSnapshot", "build_market_feature_snapshot"]
