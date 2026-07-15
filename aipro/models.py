from dataclasses import dataclass
from enum import Enum


class Signal(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"


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
