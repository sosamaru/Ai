from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Position:
    quantity: float
    average_price: float

    def to_dict(self) -> dict[str, float]:
        return {
            "quantity": self.quantity,
            "average_price": self.average_price,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Position:
        return cls(
            quantity=float(data["quantity"]),
            average_price=float(data["average_price"]),
        )


@dataclass(slots=True)
class PaperBroker:
    cash_krw: float
    positions: dict[str, Position] = field(default_factory=dict)

    def buy(self, symbol: str, price: float, amount_krw: int) -> None:
        if price <= 0:
            raise ValueError("price must be positive")
        if amount_krw <= 0 or amount_krw > self.cash_krw:
            raise ValueError("invalid buy amount")
        quantity = amount_krw / price
        current = self.positions.get(symbol)
        if current:
            total_qty = current.quantity + quantity
            average_price = (
                (current.quantity * current.average_price) + amount_krw
            ) / total_qty
            self.positions[symbol] = Position(total_qty, average_price)
        else:
            self.positions[symbol] = Position(quantity, price)
        self.cash_krw -= amount_krw

    def sell_all(self, symbol: str, price: float) -> float:
        if price <= 0:
            raise ValueError("price must be positive")
        position = self.positions.pop(symbol, None)
        if not position:
            return 0.0
        proceeds = position.quantity * price
        self.cash_krw += proceeds
        return proceeds

    def equity(self, prices: dict[str, float]) -> float:
        position_value = sum(
            position.quantity * prices.get(symbol, position.average_price)
            for symbol, position in self.positions.items()
        )
        return self.cash_krw + position_value

    def to_dict(self) -> dict[str, Any]:
        return {
            "cash_krw": self.cash_krw,
            "positions": {
                symbol: position.to_dict()
                for symbol, position in self.positions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaperBroker:
        raw_positions = data.get("positions", {})
        if not isinstance(raw_positions, dict):
            raise ValueError("positions must be a mapping")
        positions = {
            str(symbol): Position.from_dict(position)
            for symbol, position in raw_positions.items()
        }
        return cls(cash_krw=float(data["cash_krw"]), positions=positions)
