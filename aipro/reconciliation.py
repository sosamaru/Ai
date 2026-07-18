from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass

from aipro.broker import PaperBroker
from aipro.models import OrderSide, OrderStatus


@dataclass(frozen=True, slots=True)
class ReconciliationIssue:
    code: str
    message: str
    symbol: str | None = None
    expected: float | None = None
    actual: float | None = None


@dataclass(frozen=True, slots=True)
class ReconciliationReport:
    expected_cash_krw: float
    actual_cash_krw: float
    issues: tuple[ReconciliationIssue, ...]

    @property
    def is_consistent(self) -> bool:
        return not self.issues


def reconcile_paper_account(
    broker: PaperBroker,
    initial_cash_krw: float,
    *,
    absolute_tolerance: float = 1e-6,
) -> ReconciliationReport:
    """Rebuild cash and net quantities from immutable order records without mutating state."""
    if not math.isfinite(initial_cash_krw) or initial_cash_krw < 0:
        raise ValueError("initial_cash_krw must be finite and non-negative")
    if not math.isfinite(absolute_tolerance) or absolute_tolerance < 0:
        raise ValueError("absolute_tolerance must be finite and non-negative")

    expected_cash = float(initial_cash_krw)
    expected_quantities: dict[str, float] = defaultdict(float)
    issues: list[ReconciliationIssue] = []

    for order_id, order in broker.orders.items():
        if order_id != order.client_order_id:
            issues.append(
                ReconciliationIssue(
                    code="ORDER_ID_MISMATCH",
                    message="order dictionary key differs from client order id",
                    symbol=order.symbol,
                )
            )
        if order.status is not OrderStatus.FILLED:
            continue
        if order.side is OrderSide.BUY:
            expected_cash -= order.amount_krw
            expected_quantities[order.symbol] += order.quantity
        elif order.side is OrderSide.SELL:
            expected_cash += order.amount_krw
            expected_quantities[order.symbol] -= order.quantity

    if not math.isclose(
        expected_cash,
        broker.cash_krw,
        rel_tol=0.0,
        abs_tol=absolute_tolerance,
    ):
        issues.append(
            ReconciliationIssue(
                code="CASH_MISMATCH",
                message="cash does not match the value reconstructed from filled orders",
                expected=expected_cash,
                actual=broker.cash_krw,
            )
        )

    symbols = set(expected_quantities) | set(broker.positions)
    for symbol in sorted(symbols):
        expected = expected_quantities.get(symbol, 0.0)
        actual_position = broker.positions.get(symbol)
        actual = 0.0 if actual_position is None else actual_position.quantity
        if expected < -absolute_tolerance:
            issues.append(
                ReconciliationIssue(
                    code="NEGATIVE_RECONSTRUCTED_POSITION",
                    message="filled sell quantity exceeds filled buy quantity",
                    symbol=symbol,
                    expected=expected,
                    actual=actual,
                )
            )
            continue
        normalized_expected = 0.0 if abs(expected) <= absolute_tolerance else expected
        if not math.isclose(
            normalized_expected,
            actual,
            rel_tol=0.0,
            abs_tol=absolute_tolerance,
        ):
            issues.append(
                ReconciliationIssue(
                    code="POSITION_QUANTITY_MISMATCH",
                    message="position quantity does not match filled-order reconstruction",
                    symbol=symbol,
                    expected=normalized_expected,
                    actual=actual,
                )
            )

    return ReconciliationReport(
        expected_cash_krw=expected_cash,
        actual_cash_krw=broker.cash_krw,
        issues=tuple(issues),
    )
