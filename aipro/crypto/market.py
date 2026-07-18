from __future__ import annotations

import json
import math
import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from aipro.models import MarketSnapshot

UPBIT_API_BASE_URL = "https://api.upbit.com"
DEFAULT_UPBIT_SYMBOLS = ("KRW-BTC", "KRW-ETH", "KRW-XRP")


class MarketDataError(RuntimeError):
    """Raised when public market data cannot be retrieved or validated."""


class HttpResponse(Protocol):
    def read(self) -> bytes: ...

    def __enter__(self) -> HttpResponse: ...

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None: ...


OpenUrl = Callable[..., HttpResponse]
Sleep = Callable[[float], None]


class DemoMarketData:
    """Deterministic crypto market data for offline smoke tests."""

    def snapshots(self) -> list[MarketSnapshot]:
        return [
            MarketSnapshot("KRW-BTC", 150_000_000.0, 1.2, 2.1),
            MarketSnapshot("KRW-ETH", 5_000_000.0, 0.2, 1.8),
            MarketSnapshot("KRW-XRP", 3_000.0, -1.4, 3.0),
        ]


@dataclass(frozen=True, slots=True)
class UpbitPublicClient:
    """Minimal unauthenticated client for Upbit quotation endpoints only."""

    base_url: str = UPBIT_API_BASE_URL
    timeout_sec: float = 5.0
    max_attempts: int = 3
    backoff_sec: float = 0.25
    opener: OpenUrl = urlopen
    sleep: Sleep = time.sleep

    def __post_init__(self) -> None:
        if not self.base_url.startswith("https://"):
            raise ValueError("Upbit base_url must use HTTPS")
        if self.timeout_sec <= 0:
            raise ValueError("timeout_sec must be positive")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.backoff_sec < 0:
            raise ValueError("backoff_sec must be non-negative")

    def get_json(self, path: str, params: dict[str, object]) -> object:
        query = urlencode(params)
        request = Request(
            f"{self.base_url.rstrip('/')}{path}?{query}",
            headers={
                "Accept": "application/json",
                "User-Agent": "AiPro/readonly-market-data",
            },
            method="GET",
        )

        last_error: BaseException | None = None
        for attempt in range(1, self.max_attempts + 1):
            try:
                with self.opener(request, timeout=self.timeout_sec) as response:
                    raw = response.read()
                return json.loads(raw.decode("utf-8"))
            except HTTPError as exc:
                last_error = exc
                if exc.code not in {429, 500, 502, 503, 504}:
                    break
            except (URLError, TimeoutError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                last_error = exc

            if attempt < self.max_attempts:
                self.sleep(self.backoff_sec * attempt)

        raise MarketDataError(f"Upbit public API request failed: {path}") from last_error


@dataclass(frozen=True, slots=True)
class TickerPoint:
    price: float
    timestamp: datetime


@dataclass(frozen=True, slots=True)
class CandleSeries:
    closes: list[float]
    newest_timestamp: datetime


@dataclass(slots=True)
class UpbitMarketData:
    """Read-only Upbit market adapter producing timestamped snapshots."""

    symbols: tuple[str, ...] = DEFAULT_UPBIT_SYMBOLS
    client: UpbitPublicClient = UpbitPublicClient()
    candle_count: int = 25

    def __post_init__(self) -> None:
        normalized = tuple(symbol.strip().upper() for symbol in self.symbols)
        if not normalized or any(not symbol for symbol in normalized):
            raise ValueError("at least one non-empty Upbit symbol is required")
        if len(set(normalized)) != len(normalized):
            raise ValueError("Upbit symbols must be unique")
        if any(not symbol.startswith("KRW-") for symbol in normalized):
            raise ValueError("current crypto runtime supports KRW Upbit symbols only")
        if not 2 <= self.candle_count <= 200:
            raise ValueError("candle_count must be between 2 and 200")
        self.symbols = normalized

    def snapshots(self) -> list[MarketSnapshot]:
        ticker_payload = self.client.get_json(
            "/v1/ticker",
            {"markets": ",".join(self.symbols)},
        )
        tickers = self._ticker_points(ticker_payload)

        snapshots: list[MarketSnapshot] = []
        for symbol in self.symbols:
            if symbol not in tickers:
                raise MarketDataError(f"Upbit ticker response missing symbol: {symbol}")
            candle_payload = self.client.get_json(
                "/v1/candles/minutes/60",
                {"market": symbol, "count": self.candle_count},
            )
            candles = self._candle_series(candle_payload, symbol)
            ticker = tickers[symbol]
            change_1h_pct = (ticker.price / candles.closes[1] - 1.0) * 100.0
            volatility_pct = self._return_volatility_pct(candles.closes)
            snapshots.append(
                MarketSnapshot(
                    symbol=symbol,
                    price=ticker.price,
                    change_1h_pct=change_1h_pct,
                    volatility_pct=volatility_pct,
                    ticker_timestamp=ticker.timestamp,
                    candle_timestamp=candles.newest_timestamp,
                )
            )
        return snapshots

    @staticmethod
    def _ticker_points(payload: object) -> dict[str, TickerPoint]:
        if not isinstance(payload, list) or not payload:
            raise MarketDataError("Upbit ticker response must be a non-empty list")
        points: dict[str, TickerPoint] = {}
        for item in payload:
            if not isinstance(item, dict):
                raise MarketDataError("Upbit ticker item must be an object")
            try:
                symbol = str(item["market"]).upper()
                price = float(item["trade_price"])
                timestamp = UpbitMarketData._timestamp_from_millis(item["timestamp"])
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise MarketDataError("invalid Upbit ticker item") from exc
            if not symbol or not math.isfinite(price) or price <= 0:
                raise MarketDataError("invalid Upbit ticker price")
            if symbol in points:
                raise MarketDataError(f"duplicate Upbit ticker symbol: {symbol}")
            points[symbol] = TickerPoint(price=price, timestamp=timestamp)
        return points

    @staticmethod
    def _candle_series(payload: object, symbol: str) -> CandleSeries:
        if not isinstance(payload, list) or len(payload) < 2:
            raise MarketDataError(f"insufficient Upbit hourly candles: {symbol}")
        closes: list[float] = []
        newest_timestamp: datetime | None = None
        previous_timestamp: datetime | None = None
        for item in payload:
            if not isinstance(item, dict):
                raise MarketDataError("Upbit candle item must be an object")
            try:
                market = str(item["market"]).upper()
                close = float(item["trade_price"])
                timestamp = UpbitMarketData._timestamp_from_utc_text(
                    item["candle_date_time_utc"]
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise MarketDataError("invalid Upbit candle item") from exc
            if market != symbol or not math.isfinite(close) or close <= 0:
                raise MarketDataError(f"invalid Upbit candle for {symbol}")
            if previous_timestamp is not None and timestamp >= previous_timestamp:
                raise MarketDataError(
                    f"Upbit candles must be newest-first with unique timestamps: {symbol}"
                )
            if newest_timestamp is None:
                newest_timestamp = timestamp
            previous_timestamp = timestamp
            closes.append(close)
        assert newest_timestamp is not None
        return CandleSeries(closes=closes, newest_timestamp=newest_timestamp)

    @staticmethod
    def _timestamp_from_millis(value: object) -> datetime:
        milliseconds = float(value)
        if not math.isfinite(milliseconds) or milliseconds <= 0:
            raise ValueError("timestamp must be a positive finite number")
        return datetime.fromtimestamp(milliseconds / 1000.0, tz=timezone.utc)

    @staticmethod
    def _timestamp_from_utc_text(value: object) -> datetime:
        text = str(value).strip()
        if not text:
            raise ValueError("timestamp text is empty")
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @staticmethod
    def _return_volatility_pct(closes_newest_first: list[float]) -> float:
        chronological = list(reversed(closes_newest_first))
        returns = [
            (current / previous - 1.0) * 100.0
            for previous, current in zip(chronological, chronological[1:])
        ]
        if len(returns) < 2:
            return 0.0
        value = statistics.pstdev(returns)
        if not math.isfinite(value) or value < 0:
            raise MarketDataError("calculated Upbit volatility is invalid")
        return value


__all__ = [
    "DEFAULT_UPBIT_SYMBOLS",
    "DemoMarketData",
    "MarketDataError",
    "UPBIT_API_BASE_URL",
    "UpbitMarketData",
    "UpbitPublicClient",
]
