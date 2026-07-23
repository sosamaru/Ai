from datetime import UTC, datetime, timedelta

import pytest

from aipro.intelligence.market_features import MarketBar, MarketFeaturePolicy, build_market_feature_snapshot


def bars(count: int = 30, *, end: datetime | None = None):
    end_time = end or datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
    result = []
    for index in range(count):
        close = 100.0 + index
        result.append(
            MarketBar(
                timestamp_utc=(end_time - timedelta(minutes=count - 1 - index)).isoformat(),
                open=close - 0.5,
                high=close + 1.0,
                low=close - 1.0,
                close=close,
                volume=1000.0 + index * 10,
                quote_volume=close * (1000.0 + index * 10),
                bid_ask_spread_bps=5.0,
            )
        )
    return tuple(result)


def test_snapshot_is_deterministic_and_eligible() -> None:
    as_of = datetime(2026, 7, 23, 9, 0, tzinfo=UTC)
    first = build_market_feature_snapshot("btc", bars(end=as_of), as_of_utc=as_of)
    second = build_market_feature_snapshot("BTC", bars(end=as_of), as_of_utc=as_of)

    assert first == second
    assert first.symbol == "BTC"
    assert first.eligible is True
    assert first.return_short_pct > 0
    assert first.return_medium_pct > first.return_short_pct
    assert first.volume_ratio > 1
    assert first.spread_bps_average == 5.0
    assert len(first.fingerprint) == 64


def test_insufficient_and_stale_data_fail_closed() -> None:
    end = datetime(2026, 7, 23, 8, 0, tzinfo=UTC)
    snapshot = build_market_feature_snapshot(
        "AAPL",
        bars(10, end=end),
        as_of_utc=datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
    )
    assert snapshot.eligible is False
    assert "INSUFFICIENT_BARS" in snapshot.ineligible_reasons
    assert "STALE_MARKET_DATA" in snapshot.ineligible_reasons


def test_excess_zero_volume_fails_closed() -> None:
    source = list(bars())
    for index in range(10):
        item = source[index]
        source[index] = MarketBar(
            timestamp_utc=item.timestamp_utc,
            open=item.open,
            high=item.high,
            low=item.low,
            close=item.close,
            volume=0.0,
            quote_volume=0.0,
            bid_ask_spread_bps=item.bid_ask_spread_bps,
        )
    snapshot = build_market_feature_snapshot(
        "BTC",
        source,
        as_of_utc=datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
    )
    assert snapshot.eligible is False
    assert "EXCESS_ZERO_VOLUME" in snapshot.ineligible_reasons


def test_invalid_bar_and_duplicate_timestamp_are_rejected() -> None:
    with pytest.raises(ValueError, match="OHLC"):
        MarketBar(
            timestamp_utc="2026-07-23T09:00:00+00:00",
            open=100,
            high=99,
            low=98,
            close=100,
            volume=1,
        )

    duplicate = list(bars())
    duplicate[-1] = duplicate[-2]
    with pytest.raises(ValueError, match="duplicate"):
        build_market_feature_snapshot(
            "BTC",
            duplicate,
            as_of_utc=datetime(2026, 7, 23, 9, 0, tzinfo=UTC),
        )


def test_policy_rejects_invalid_windows() -> None:
    with pytest.raises(ValueError, match="windows"):
        MarketFeaturePolicy(minimum_bars=30, short_window=20, medium_window=5)
