from dataclasses import dataclass
from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(str, Enum):
    FILLED = "FILLED"
    NO_POSITION = "NO_POSITION"


@dataclass(frozen=True, slots=True)
class MarketSnapshot:
    symbol: str
    price: float
    change_1h_pct: float
    volatility_pct: float


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
