from dataclasses import dataclass, field


@dataclass(slots=True)
class Position:
    quantity: float
    average_price: float


@dataclass(slots=True)
class PaperBroker:
    cash_krw: float
    positions: dict[str, Position] = field(default_factory=dict)

    def buy(self, symbol: str, price: float, amount_krw: int) -> None:
        if amount_krw <= 0 or amount_krw > self.cash_krw:
            raise ValueError("invalid buy amount")
        quantity = amount_krw / price
        current = self.positions.get(symbol)
        if current:
            total_qty = current.quantity + quantity
            avg = ((current.quantity * current.average_price) + amount_krw) / total_qty
            self.positions[symbol] = Position(total_qty, avg)
        else:
            self.positions[symbol] = Position(quantity, price)
        self.cash_krw -= amount_krw

    def sell_all(self, symbol: str, price: float) -> float:
        position = self.positions.pop(symbol, None)
        if not position:
            return 0.0
        proceeds = position.quantity * price
        self.cash_krw += proceeds
        return proceeds

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash_krw + sum(pos.quantity * prices.get(symbol, pos.average_price) for symbol, pos in self.positions.items())
