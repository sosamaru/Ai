from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from aipro.broker import Fill, PaperBroker


class Exchange(Protocol):
    def buy(self, symbol: str, price: float, amount_krw: int) -> Fill: ...
    def sell_all(self, symbol: str, price: float) -> Fill | None: ...
    def equity(self, prices: dict[str, float]) -> float: ...


@dataclass(slots=True)
class FakeExchange:
    broker: PaperBroker

    def buy(self, symbol: str, price: float, amount_krw: int) -> Fill:
        return self.broker.buy(symbol, price, amount_krw)

    def sell_all(self, symbol: str, price: float) -> Fill | None:
        return self.broker.sell_all(symbol, price)

    def equity(self, prices: dict[str, float]) -> float:
        return self.broker.equity(prices)
