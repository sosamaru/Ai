from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.error import URLError

import pytest

from aipro.config import Settings
from aipro.crypto.application import CryptoTradingApplication
from aipro.crypto.market import MarketDataError, UpbitMarketData, UpbitPublicClient
from aipro.crypto.market_health import HealthCheckedMarketData


class FakeResponse:
    def __init__(self, payload: object) -> None:
        self.payload = json.dumps(payload).encode("utf-8")

    def read(self) -> bytes:
        return self.payload

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None


def _ticker(
    symbol: str,
    price: float,
    timestamp_ms: int = 1_768_435_200_000,
) -> dict[str, object]:
    return {"market": symbol, "trade_price": price, "timestamp": timestamp_ms}


def _candle(
    symbol: str,
    price: float,
    timestamp: str,
) -> dict[str, object]:
    return {
        "market": symbol,
        "trade_price": price,
        "candle_date_time_utc": timestamp,
    }


def test_upbit_market_data_builds_timestamped_strategy_snapshots() -> None:
    responses = [
        FakeResponse([_ticker("KRW-BTC", 110.0)]),
        FakeResponse(
            [
                _candle("KRW-BTC", 109.0, "2026-01-15T00:00:00"),
                _candle("KRW-BTC", 100.0, "2026-01-14T23:00:00"),
                _candle("KRW-BTC", 95.0, "2026-01-14T22:00:00"),
            ]
        ),
    ]
    urls: list[str] = []

    def opener(request, timeout: float):
        urls.append(request.full_url)
        assert timeout == 2.0
        return responses.pop(0)

    client = UpbitPublicClient(timeout_sec=2.0, max_attempts=1, opener=opener)
    market = UpbitMarketData(symbols=("krw-btc",), client=client, candle_count=3)

    snapshots = market.snapshots()

    assert len(snapshots) == 1
    assert snapshots[0].symbol == "KRW-BTC"
    assert snapshots[0].price == 110.0
    assert snapshots[0].change_1h_pct == pytest.approx(10.0)
    assert snapshots[0].volatility_pct >= 0.0
    assert snapshots[0].ticker_timestamp == datetime(
        2026, 1, 15, tzinfo=timezone.utc
    )
    assert snapshots[0].candle_timestamp == datetime(
        2026, 1, 15, tzinfo=timezone.utc
    )
    assert "/v1/ticker?markets=KRW-BTC" in urls[0]
    assert "/v1/candles/minutes/60?market=KRW-BTC&count=3" in urls[1]


def test_public_client_retries_transient_transport_failure() -> None:
    calls = 0
    sleeps: list[float] = []

    def opener(request, timeout: float):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise URLError("temporary")
        return FakeResponse([_ticker("KRW-BTC", 100.0)])

    client = UpbitPublicClient(
        max_attempts=2,
        backoff_sec=0.5,
        opener=opener,
        sleep=sleeps.append,
    )

    payload = client.get_json("/v1/ticker", {"markets": "KRW-BTC"})

    assert isinstance(payload, list)
    assert calls == 2
    assert sleeps == [0.5]


def test_public_client_raises_after_retry_exhaustion() -> None:
    def opener(request, timeout: float):
        raise URLError("offline")

    client = UpbitPublicClient(
        max_attempts=2,
        backoff_sec=0.0,
        opener=opener,
        sleep=lambda _: None,
    )

    with pytest.raises(MarketDataError, match="request failed"):
        client.get_json("/v1/ticker", {"markets": "KRW-BTC"})


def test_invalid_or_incomplete_upbit_payload_is_rejected() -> None:
    responses = [FakeResponse([_ticker("KRW-ETH", 100.0)])]

    def opener(request, timeout: float):
        return responses.pop(0)

    market = UpbitMarketData(
        symbols=("KRW-BTC",),
        client=UpbitPublicClient(max_attempts=1, opener=opener),
    )

    with pytest.raises(MarketDataError, match="missing symbol"):
        market.snapshots()


def test_missing_ticker_timestamp_is_rejected() -> None:
    responses = [FakeResponse([{"market": "KRW-BTC", "trade_price": 100.0}])]

    def opener(request, timeout: float):
        return responses.pop(0)

    market = UpbitMarketData(
        symbols=("KRW-BTC",),
        client=UpbitPublicClient(max_attempts=1, opener=opener),
    )

    with pytest.raises(MarketDataError, match="invalid Upbit ticker item"):
        market.snapshots()


def test_duplicate_or_out_of_order_candle_timestamp_is_rejected() -> None:
    responses = [
        FakeResponse([_ticker("KRW-BTC", 110.0)]),
        FakeResponse(
            [
                _candle("KRW-BTC", 109.0, "2026-01-15T00:00:00"),
                _candle("KRW-BTC", 100.0, "2026-01-15T00:00:00"),
            ]
        ),
    ]

    def opener(request, timeout: float):
        return responses.pop(0)

    market = UpbitMarketData(
        symbols=("KRW-BTC",),
        client=UpbitPublicClient(max_attempts=1, opener=opener),
        candle_count=2,
    )

    with pytest.raises(MarketDataError, match="newest-first"):
        market.snapshots()


def test_upbit_provider_is_opt_in_and_does_not_enable_live(tmp_path) -> None:
    settings = Settings(
        db_path=tmp_path / "aipro.db",
        market_data_provider="UPBIT",
        crypto_symbols=("KRW-BTC",),
    )
    settings.validate()

    app = CryptoTradingApplication(settings)

    assert isinstance(app.market, UpbitMarketData)
    assert isinstance(app.market_health, HealthCheckedMarketData)
    assert app.market_health.delegate is app.market
    assert app.settings.mode == "PAPER"
    assert app.settings.enable_live_trading is False


def test_market_data_settings_reject_unsafe_or_invalid_values() -> None:
    with pytest.raises(ValueError, match="DEMO or UPBIT"):
        Settings(market_data_provider="OTHER").validate()
    with pytest.raises(ValueError, match="KRW Upbit pairs"):
        Settings(crypto_symbols=("BTC-USDT",)).validate()
    with pytest.raises(ValueError, match="between 1 and 5"):
        Settings(market_data_max_attempts=10).validate()
