"""Strict point-in-time input contract for local US-stock PAPER execution.

Frames must come from a trusted data adapter. A JSON file is an input transport,
not authentication or proof of broker eligibility. Demo frames are synthetic.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from zoneinfo import ZoneInfo

from aipro.intelligence.market_features import MarketBar
from aipro.us_stocks.portfolio_policy import number

NY = ZoneInfo("America/New_York")


def instant(value: str | datetime) -> datetime:
    result = datetime.fromisoformat(value) if isinstance(value, str) else value
    if not isinstance(result, datetime) or result.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return result.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Intelligence:
    as_of_utc: datetime
    news_sentiment: float = 0.0
    macro_risk_off: bool = False
    material_risk: bool = False
    source: str = "operator-input"
    feature_fingerprint: str = ""

    def __post_init__(self) -> None:
        instant(self.as_of_utc)
        if not math.isfinite(self.news_sentiment) or not -1 <= self.news_sentiment <= 1:
            raise ValueError("invalid sentiment")
        if type(self.macro_risk_off) is not bool or type(self.material_risk) is not bool:
            raise ValueError("risk flags must be booleans")
        if not self.source.strip():
            raise ValueError("intelligence source required")
        if self.feature_fingerprint and not re.fullmatch(r"[a-f0-9]{64}", self.feature_fingerprint):
            raise ValueError("invalid combined-feature fingerprint")


@dataclass(frozen=True, slots=True)
class Quote:
    symbol: str
    as_of_utc: datetime
    bid: Decimal
    ask: Decimal
    bid_size: Decimal
    ask_size: Decimal
    daily_dollar_volume: Decimal
    intraday_bars: tuple[MarketBar, ...] = ()
    daily_bars: tuple[MarketBar, ...] = ()
    intelligence: Intelligence | None = None
    fractionable: bool = False
    tradable: bool = True

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", self.symbol):
            raise ValueError("normalized US symbol required")
        instant(self.as_of_utc)
        for key in ("bid", "ask", "bid_size", "ask_size", "daily_dollar_volume"):
            number(getattr(self, key))
        if self.bid <= 0 or self.ask < self.bid:
            raise ValueError("invalid bid/ask")
        if type(self.fractionable) is not bool or type(self.tradable) is not bool:
            raise ValueError("asset flags must be booleans")
        for bars in (self.intraday_bars, self.daily_bars):
            if len(bars) > 2000:
                raise ValueError("too many bars")
            times = [instant(bar.timestamp_utc) for bar in bars]
            if times != sorted(set(times)) or any(t > instant(self.as_of_utc) for t in times):
                raise ValueError("bars must be unique, chronological, and observable at quote time")

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def spread_bps(self) -> Decimal:
        return (self.ask - self.bid) / self.mid * 10000


@dataclass(frozen=True, slots=True)
class MarketFrame:
    as_of_utc: datetime
    usd_krw: Decimal
    fx_as_of_utc: datetime
    session_open_utc: datetime
    session_close_utc: datetime
    settlement_at_utc: datetime
    quotes: tuple[Quote, ...]
    source: str
    synthetic: bool = False

    def __post_init__(self) -> None:
        now = instant(self.as_of_utc)
        opened, closed = instant(self.session_open_utc), instant(self.session_close_utc)
        instant(self.fx_as_of_utc)
        if number(self.usd_krw) <= 0:
            raise ValueError("positive FX rate required")
        if not opened < closed or closed - opened > timedelta(hours=7):
            raise ValueError("invalid regular session window")
        local_open, local_close = opened.astimezone(NY), closed.astimezone(NY)
        if (local_open.date() != local_close.date() or local_open.weekday() >= 5
                or (local_open.hour, local_open.minute) != (9, 30)
                or (local_close.hour, local_close.minute) > (16, 0)):
            raise ValueError("US regular-session calendar window required")
        if instant(self.settlement_at_utc) <= max(now, closed):
            raise ValueError("future broker-supplied settlement timestamp required")
        if not self.source.strip() or type(self.synthetic) is not bool:
            raise ValueError("source and boolean synthetic marker required")
        symbols = [quote.symbol for quote in self.quotes]
        if len(symbols) > 100 or len(symbols) != len(set(symbols)):
            raise ValueError("too many or duplicate symbols")

    @property
    def fingerprint(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), default=str))

    @classmethod
    def from_dict(cls, payload: dict) -> "MarketFrame":
        values = dict(payload)
        quotes = []
        for raw in values.pop("quotes"):
            item = dict(raw)
            for key in ("bid", "ask", "bid_size", "ask_size", "daily_dollar_volume"):
                item[key] = number(item[key])
            item["as_of_utc"] = instant(item["as_of_utc"])
            for key in ("intraday_bars", "daily_bars"):
                item[key] = tuple(MarketBar(**bar) for bar in item.get(key, ()))
            intelligence = item.get("intelligence")
            if intelligence is not None:
                intelligence = dict(intelligence)
                intelligence["as_of_utc"] = instant(intelligence["as_of_utc"])
                item["intelligence"] = Intelligence(**intelligence)
            quotes.append(Quote(**item))
        for key in ("as_of_utc", "fx_as_of_utc", "session_open_utc", "session_close_utc", "settlement_at_utc"):
            values[key] = instant(values[key])
        values["usd_krw"] = number(values["usd_krw"])
        return cls(quotes=tuple(quotes), **values)


class FileMarketData:
    def __init__(self, path: Path) -> None:
        self.path = path

    def frame(self) -> MarketFrame:
        with self.path.open("rb") as handle:
            raw = handle.read(8_000_001)
        if len(raw) > 8_000_000:
            raise ValueError("market frame exceeds 8 MB")
        return MarketFrame.from_dict(json.loads(raw))


def intelligence_from_components(*, symbol: str, as_of_utc: datetime,
                                 news, macro, filings, market) -> Intelligence | None:
    """Bridge existing news/FRED/SEC/market features without inventing missing data.

    The caller must resolve the correct company CIK and supply completed,
    point-in-time component snapshots. A securities offering is a conservative
    entry veto; other material events still need the existing filing review.
    """
    from aipro.intelligence.combined_features import build_combined_paper_feature_vector
    now = instant(as_of_utc)
    observed = [instant(item.observed_at_utc) for item in macro.observations]
    filed = [instant(event.filed_at_utc) for event in filings.events]
    if any(value > now for value in observed + filed):
        return None
    if news.freshest_article_at_utc and instant(news.freshest_article_at_utc) > now:
        return None
    vector = build_combined_paper_feature_vector(symbol=symbol, as_of_utc=now,
        news=news, macro=macro, filings=filings, market=market)
    if not vector.eligible or any(not math.isfinite(value) for value in vector.values):
        return None
    if any(not 0 <= (now - instant(component.as_of_utc)).total_seconds() <= 300
           for component in (news, macro, filings, market)):
        return None
    features = vector.as_mapping()
    # Preserve the provider-native score when there is relevant native evidence.
    score = features["news_native_sentiment"] if features["news_native_relevance"] > 0 else features["news_fused_sentiment"]
    return Intelligence(now, score, bool(features["macro_risk_off"]),
        features["filing_offering_count"] > 0, "aipro-combined-feature-vector", vector.fingerprint)
