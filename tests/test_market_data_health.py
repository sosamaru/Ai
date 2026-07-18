from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from aipro.crypto.market_health import (
    HealthCheckedMarketData,
    MarketDataHealthError,
    MarketDataHealthPolicy,
)
from aipro.models import MarketSnapshot


class StaticProvider:
    def snapshots(self) -> list[MarketSnapshot]:
        return [MarketSnapshot("KRW-BTC", 100.0, 1.0, 2.0)]


class FailingProvider:
    def snapshots(self) -> list[MarketSnapshot]:
        raise RuntimeError("network down")


def test_health_gate_records_success_and_latency() -> None:
    ticks = iter((10.0, 10.25))
    now = datetime(2026, 7, 18, tzinfo=timezone.utc)
    market = HealthCheckedMarketData(
        provider_name="UPBIT",
        delegate=StaticProvider(),
        monotonic=lambda: next(ticks),
        now=lambda: now,
    )

    assert market.snapshots()[0].symbol == "KRW-BTC"
    status = market.health_status()
    assert status["healthy"] is True
    assert status["last_latency_sec"] == pytest.approx(0.25)
    assert status["consecutive_failures"] == 0


def test_latency_limit_fails_closed() -> None:
    ticks = iter((1.0, 4.0))
    market = HealthCheckedMarketData(
        provider_name="UPBIT",
        delegate=StaticProvider(),
        policy=MarketDataHealthPolicy(max_latency_sec=1.0),
        monotonic=lambda: next(ticks),
    )

    with pytest.raises(MarketDataHealthError, match="latency"):
        market.snapshots()
    assert market.consecutive_failures == 1
    assert market.health_status()["healthy"] is False


def test_failures_are_counted_and_success_resets_counter() -> None:
    market = HealthCheckedMarketData(provider_name="UPBIT", delegate=FailingProvider())
    with pytest.raises(MarketDataHealthError, match="network down"):
        market.snapshots()
    assert market.consecutive_failures == 1

    market.delegate = StaticProvider()
    market.snapshots()
    assert market.consecutive_failures == 0
    assert market.last_error is None


def test_stale_last_success_is_rejected() -> None:
    current = datetime(2026, 7, 18, tzinfo=timezone.utc)
    market = HealthCheckedMarketData(
        provider_name="UPBIT",
        delegate=StaticProvider(),
        policy=MarketDataHealthPolicy(max_snapshot_age_sec=30.0),
        now=lambda: current,
    )
    market.last_success_at = current - timedelta(seconds=31)

    with pytest.raises(MarketDataHealthError, match="stale"):
        market.assert_fresh()
    assert market.health_status()["healthy"] is False


def test_invalid_health_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_latency_sec"):
        MarketDataHealthPolicy(max_latency_sec=0)
    with pytest.raises(ValueError, match="max_snapshot_age_sec"):
        MarketDataHealthPolicy(max_snapshot_age_sec=0)
    with pytest.raises(ValueError, match="max_consecutive_failures"):
        MarketDataHealthPolicy(max_consecutive_failures=0)
