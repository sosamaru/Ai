from __future__ import annotations

from dataclasses import dataclass, field

from aipro.storage import Storage


@dataclass(slots=True)
class Position:
    quantity: float
    average_price: float


@dataclass(slots=True)
class PaperBroker:
    cash_krw: float
    positions: dict[str, Position] = field(default_factory=dict)
    storage: Storage | None = None

    @classmethod
    def restore(cls, storage: Storage, initial_cash_krw: float) -> PaperBroker:
        persisted = storage.load_paper_account()
        if persisted is None:
            broker = cls(float(initial_cash_krw), storage=storage)
            broker._persist()
            return broker

        cash_krw, raw_positions = persisted
        positions = {
            symbol: Position(quantity=quantity, average_price=average_price)
            for symbol, (quantity, average_price) in raw_positions.items()
        }
        return cls(cash_krw=cash_krw, positions=positions, storage=storage)

    def _position_snapshot(self) -> dict[str, tuple[float, float]]:
        return {
            symbol: (position.quantity, position.average_price)
            for symbol, position in self.positions.items()
        }

    def _persist(self, transaction: dict[str, object] | None = None) -> None:
        if self.storage is None:
            return
        self.storage.save_paper_account(
            cash_krw=self.cash_krw,
            positions=self._position_snapshot(),
            transaction=transaction,
        )

    def buy(self, symbol: str, price: float, amount_krw: int) -> None:
        if not symbol or price <= 0:
            raise ValueError("invalid buy order")
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
        self._persist(
            {
                "side": "BUY",
                "symbol": symbol,
                "quantity": quantity,
                "price": price,
                "gross_krw": float(amount_krw),
            }
        )

    def sell_all(self, symbol: str, price: float) -> float:
        if not symbol or price <= 0:
            raise ValueError("invalid sell order")
        position = self.positions.pop(symbol, None)
        if not position:
            return 0.0

        proceeds = position.quantity * price
        self.cash_krw += proceeds
        self._persist(
            {
                "side": "SELL",
                "symbol": symbol,
                "quantity": position.quantity,
                "price": price,
                "gross_krw": proceeds,
            }
        )
        return proceeds

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash_krw + sum(
            position.quantity * prices.get(symbol, position.average_price)
            for symbol, position in self.positions.items()
        )
