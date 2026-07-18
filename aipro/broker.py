from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Protocol

LOGGER = logging.getLogger(__name__)
PAPER_ACCOUNT_STATE_KEY = "paper_account"


class StateStore(Protocol):
    def get_state(self, key: str) -> str | None: ...

    def set_state(self, key: str, value: str) -> None: ...

    def record(self, event_type: str, payload: str) -> None: ...


@dataclass(slots=True)
class Position:
    quantity: float
    average_price: float


@dataclass(slots=True)
class PaperBroker:
    cash_krw: float
    positions: dict[str, Position] = field(default_factory=dict)
    storage: StateStore | None = field(default=None, repr=False)

    @classmethod
    def restore(cls, initial_cash_krw: float, storage: StateStore) -> PaperBroker:
        raw = storage.get_state(PAPER_ACCOUNT_STATE_KEY)
        if raw is None:
            broker = cls(float(initial_cash_krw), storage=storage)
            broker._persist("paper_account_initialized")
            return broker

        try:
            payload = json.loads(raw)
            cash_krw = float(payload["cash_krw"])
            raw_positions = payload.get("positions", {})
            if not isinstance(raw_positions, dict):
                raise ValueError("positions must be an object")
            positions = {
                str(symbol): Position(
                    quantity=float(values["quantity"]),
                    average_price=float(values["average_price"]),
                )
                for symbol, values in raw_positions.items()
            }
            cls._validate_account(cash_krw, positions)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.error("Invalid persisted paper account; restoring initial cash: %s", exc)
            storage.record(
                "paper_account_recovery",
                json.dumps({"reason": str(exc)}, sort_keys=True),
            )
            broker = cls(float(initial_cash_krw), storage=storage)
            broker._persist("paper_account_reinitialized")
            return broker

        return cls(cash_krw=cash_krw, positions=positions, storage=storage)

    @staticmethod
    def _validate_account(cash_krw: float, positions: dict[str, Position]) -> None:
        if not math.isfinite(cash_krw) or cash_krw < 0:
            raise ValueError("cash must be finite and non-negative")
        for symbol, position in positions.items():
            if not symbol:
                raise ValueError("position symbol must not be empty")
            if not math.isfinite(position.quantity) or position.quantity <= 0:
                raise ValueError(f"invalid quantity for {symbol}")
            if not math.isfinite(position.average_price) or position.average_price <= 0:
                raise ValueError(f"invalid average price for {symbol}")

    def _serialize(self) -> str:
        return json.dumps(
            {
                "cash_krw": self.cash_krw,
                "positions": {
                    symbol: {
                        "quantity": position.quantity,
                        "average_price": position.average_price,
                    }
                    for symbol, position in sorted(self.positions.items())
                },
            },
            sort_keys=True,
            separators=(",", ":"),
        )

    def _persist(self, event_type: str, **details: object) -> None:
        if self.storage is None:
            return
        self.storage.set_state(PAPER_ACCOUNT_STATE_KEY, self._serialize())
        self.storage.record(event_type, json.dumps(details, sort_keys=True))

    def buy(self, symbol: str, price: float, amount_krw: int) -> None:
        if not symbol:
            raise ValueError("symbol is required")
        if not math.isfinite(price) or price <= 0:
            raise ValueError("price must be positive")
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
        self._persist(
            "paper_buy",
            symbol=symbol,
            price=price,
            amount_krw=amount_krw,
            quantity=quantity,
        )

    def sell_all(self, symbol: str, price: float) -> float:
        if not math.isfinite(price) or price <= 0:
            raise ValueError("price must be positive")
        position = self.positions.pop(symbol, None)
        if not position:
            return 0.0
        proceeds = position.quantity * price
        self.cash_krw += proceeds
        self._persist(
            "paper_sell_all",
            symbol=symbol,
            price=price,
            quantity=position.quantity,
            proceeds_krw=proceeds,
        )
        return proceeds

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash_krw + sum(
            pos.quantity * prices.get(symbol, pos.average_price)
            for symbol, pos in self.positions.items()
        )
