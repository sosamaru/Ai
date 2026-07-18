from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    NO_POSITION = "NO_POSITION"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    price: float
    change_1h_pct: float
    volatility_pct: float
    ticker_timestamp: datetime | None = None
    candle_timestamp: datetime | None = None


@dataclass(frozen=True, slots=True)
class Decision:
    symbol: str
    signal: Signal
    confidence: float
    reason: str


@dataclass(frozen=True, slots=True)
class OrderRecord:
    client_order_id: str
    side: OrderSide
    symbol: str
    status: OrderStatus
    price: float
    quantity: float
    amount_krw: float
