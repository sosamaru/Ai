from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Position:
    quantity: float
    average_price: float


@dataclass(frozen=True, slots=True)
class Fill:
    symbol: str
    side: str
    quantity: float
    price: float
    gross_krw: float
    fee_krw: float


@dataclass(slots=True)
class PaperBroker:
    cash_krw: float
    fee_rate: float = 0.0005
    slippage_bps: float = 10.0
    positions: dict[str, Position] = field(default_factory=dict)
    fills: list[Fill] = field(default_factory=list)

    def _execution_price(self, price: float, side: str) -> float:
        if price <= 0:
            raise ValueError("price must be positive")
        adjustment = self.slippage_bps / 10_000
        return price * (1 + adjustment if side == "BUY" else 1 - adjustment)

    def buy(self, symbol: str, price: float, amount_krw: int) -> Fill:
        if amount_krw <= 0 or amount_krw > self.cash_krw:
            raise ValueError("invalid buy amount")
        execution_price = self._execution_price(price, "BUY")
        fee = amount_krw * self.fee_rate
        net_amount = amount_krw - fee
        if net_amount <= 0:
            raise ValueError("fee exceeds buy amount")
        quantity = net_amount / execution_price
        current = self.positions.get(symbol)
        if current:
            total_qty = current.quantity + quantity
            avg = ((current.quantity * current.average_price) + net_amount) / total_qty
            self.positions[symbol] = Position(total_qty, avg)
        else:
            self.positions[symbol] = Position(quantity, execution_price)
        self.cash_krw -= amount_krw
        fill = Fill(symbol, "BUY", quantity, execution_price, float(amount_krw), fee)
        self.fills.append(fill)
        return fill

    def sell_all(self, symbol: str, price: float) -> Fill | None:
        position = self.positions.pop(symbol, None)
        if not position:
            return None
        execution_price = self._execution_price(price, "SELL")
        gross = position.quantity * execution_price
        fee = gross * self.fee_rate
        self.cash_krw += gross - fee
        fill = Fill(symbol, "SELL", position.quantity, execution_price, gross, fee)
        self.fills.append(fill)
        return fill

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash_krw + sum(
            pos.quantity * prices.get(symbol, pos.average_price)
            for symbol, pos in self.positions.items()
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "cash_krw": self.cash_krw,
            "fee_rate": self.fee_rate,
            "slippage_bps": self.slippage_bps,
            "positions": {
                symbol: {
                    "quantity": position.quantity,
                    "average_price": position.average_price,
                }
                for symbol, position in self.positions.items()
            },
        }

    @classmethod
    def restore(cls, state: dict[str, Any]) -> "PaperBroker":
        broker = cls(
            cash_krw=float(state["cash_krw"]),
            fee_rate=float(state.get("fee_rate", 0.0005)),
            slippage_bps=float(state.get("slippage_bps", 10.0)),
        )
        broker.positions = {
            symbol: Position(
                quantity=float(payload["quantity"]),
                average_price=float(payload["average_price"]),
            )
            for symbol, payload in state.get("positions", {}).items()
        }
        return broker
