from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from typing import Protocol
from uuid import uuid4

from aipro.models import OrderRecord, OrderSide, OrderStatus

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
    orders: dict[str, OrderRecord] = field(default_factory=dict)
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
            raw_orders = payload.get("orders", {})
            if not isinstance(raw_positions, dict):
                raise ValueError("positions must be an object")
            if not isinstance(raw_orders, dict):
                raise ValueError("orders must be an object")

            positions = {
                str(symbol): Position(
                    quantity=float(values["quantity"]),
                    average_price=float(values["average_price"]),
                )
                for symbol, values in raw_positions.items()
            }
            orders = {
                str(order_id): OrderRecord(
                    client_order_id=str(values["client_order_id"]),
                    side=OrderSide(values["side"]),
                    symbol=str(values["symbol"]),
                    status=OrderStatus(values["status"]),
                    price=float(values["price"]),
                    quantity=float(values["quantity"]),
                    amount_krw=float(values["amount_krw"]),
                )
                for order_id, values in raw_orders.items()
            }
            cls._validate_account(cash_krw, positions, orders)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            LOGGER.error("Invalid persisted paper account; restoring initial cash: %s", exc)
            storage.record(
                "paper_account_recovery",
                json.dumps({"reason": str(exc)}, sort_keys=True),
            )
            broker = cls(float(initial_cash_krw), storage=storage)
            broker._persist("paper_account_reinitialized")
            return broker

        return cls(
            cash_krw=cash_krw,
            positions=positions,
            orders=orders,
            storage=storage,
        )

    @staticmethod
    def _validate_account(
        cash_krw: float,
        positions: dict[str, Position],
        orders: dict[str, OrderRecord],
    ) -> None:
        if not math.isfinite(cash_krw) or cash_krw < 0:
            raise ValueError("cash must be finite and non-negative")
        for symbol, position in positions.items():
            if not symbol:
                raise ValueError("position symbol must not be empty")
            if not math.isfinite(position.quantity) or position.quantity <= 0:
                raise ValueError(f"invalid quantity for {symbol}")
            if not math.isfinite(position.average_price) or position.average_price <= 0:
                raise ValueError(f"invalid average price for {symbol}")
        for order_id, order in orders.items():
            if not order_id or order_id != order.client_order_id:
                raise ValueError("invalid client order id")
            if not order.symbol:
                raise ValueError("order symbol must not be empty")
            if not math.isfinite(order.price) or order.price <= 0:
                raise ValueError(f"invalid order price for {order_id}")
            if not math.isfinite(order.quantity) or order.quantity < 0:
                raise ValueError(f"invalid order quantity for {order_id}")
            if not math.isfinite(order.amount_krw) or order.amount_krw < 0:
                raise ValueError(f"invalid order amount for {order_id}")

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
                "orders": {
                    order_id: {
                        "client_order_id": order.client_order_id,
                        "side": order.side.value,
                        "symbol": order.symbol,
                        "status": order.status.value,
                        "price": order.price,
                        "quantity": order.quantity,
                        "amount_krw": order.amount_krw,
                    }
                    for order_id, order in sorted(self.orders.items())
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

    @staticmethod
    def _normalize_order_id(client_order_id: str) -> str:
        normalized = client_order_id.strip()
        if not normalized:
            raise ValueError("client_order_id is required")
        if len(normalized) > 128:
            raise ValueError("client_order_id must be at most 128 characters")
        return normalized

    def get_order(self, client_order_id: str) -> OrderRecord | None:
        return self.orders.get(client_order_id)

    def submit_buy(
        self,
        client_order_id: str,
        symbol: str,
        price: float,
        amount_krw: int,
    ) -> OrderRecord:
        order_id = self._normalize_order_id(client_order_id)
        existing = self.orders.get(order_id)
        if existing is not None:
            return existing
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

        order = OrderRecord(
            client_order_id=order_id,
            side=OrderSide.BUY,
            symbol=symbol,
            status=OrderStatus.FILLED,
            price=price,
            quantity=quantity,
            amount_krw=float(amount_krw),
        )
        self.orders[order_id] = order
        self._persist(
            "paper_order_filled",
            client_order_id=order_id,
            side=order.side.value,
            symbol=symbol,
            price=price,
            amount_krw=amount_krw,
            quantity=quantity,
        )
        return order

    def submit_sell_all(
        self,
        client_order_id: str,
        symbol: str,
        price: float,
    ) -> OrderRecord:
        order_id = self._normalize_order_id(client_order_id)
        existing = self.orders.get(order_id)
        if existing is not None:
            return existing
        if not math.isfinite(price) or price <= 0:
            raise ValueError("price must be positive")

        position = self.positions.pop(symbol, None)
        if position is None:
            order = OrderRecord(
                client_order_id=order_id,
                side=OrderSide.SELL,
                symbol=symbol,
                status=OrderStatus.NO_POSITION,
                price=price,
                quantity=0.0,
                amount_krw=0.0,
            )
        else:
            proceeds = position.quantity * price
            self.cash_krw += proceeds
            order = OrderRecord(
                client_order_id=order_id,
                side=OrderSide.SELL,
                symbol=symbol,
                status=OrderStatus.FILLED,
                price=price,
                quantity=position.quantity,
                amount_krw=proceeds,
            )

        self.orders[order_id] = order
        self._persist(
            "paper_order_filled"
            if order.status is OrderStatus.FILLED
            else "paper_order_no_position",
            client_order_id=order_id,
            side=order.side.value,
            symbol=symbol,
            status=order.status.value,
            price=price,
            quantity=order.quantity,
            amount_krw=order.amount_krw,
        )
        return order

    def buy(self, symbol: str, price: float, amount_krw: int) -> None:
        self.submit_buy(f"auto-{uuid4().hex}", symbol, price, amount_krw)

    def sell_all(self, symbol: str, price: float) -> float:
        order = self.submit_sell_all(f"auto-{uuid4().hex}", symbol, price)
        return order.amount_krw

    def equity(self, prices: dict[str, float]) -> float:
        return self.cash_krw + sum(
            pos.quantity * prices.get(symbol, pos.average_price)
            for symbol, pos in self.positions.items()
        )
