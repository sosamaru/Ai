from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    FILLED = "FILLED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


TERMINAL_ORDER_STATUSES = frozenset(
    {OrderStatus.FILLED, OrderStatus.FAILED, OrderStatus.CANCELLED}
)

_ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.CREATED: frozenset(
        {OrderStatus.SUBMITTED, OrderStatus.FAILED, OrderStatus.CANCELLED}
    ),
    OrderStatus.SUBMITTED: frozenset(
        {OrderStatus.FILLED, OrderStatus.FAILED, OrderStatus.CANCELLED}
    ),
    OrderStatus.FILLED: frozenset(),
    OrderStatus.FAILED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}


@dataclass(frozen=True, slots=True)
class Order:
    client_order_id: str
    symbol: str
    side: OrderSide
    status: OrderStatus
    amount_krw: int | None = None
    quantity: float | None = None

    def __post_init__(self) -> None:
        if not self.client_order_id.strip():
            raise ValueError("client_order_id is required")
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if self.amount_krw is None and self.quantity is None:
            raise ValueError("amount_krw or quantity is required")
        if self.amount_krw is not None and self.amount_krw <= 0:
            raise ValueError("amount_krw must be positive")
        if self.quantity is not None and self.quantity <= 0:
            raise ValueError("quantity must be positive")


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in _ALLOWED_TRANSITIONS[current]


def require_transition(current: OrderStatus, target: OrderStatus) -> None:
    if not can_transition(current, target):
        raise ValueError(f"invalid order transition: {current} -> {target}")
