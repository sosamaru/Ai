import pytest

from aipro.orders import Order, OrderSide, OrderStatus
from aipro.storage import Storage


def test_duplicate_client_order_id_is_rejected(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    order = Order(
        client_order_id="cycle-1-btc-buy",
        symbol="KRW-BTC",
        side=OrderSide.BUY,
        status=OrderStatus.CREATED,
        amount_krw=100_000,
    )

    assert storage.create_order(order) is True
    assert storage.create_order(order) is False

    restored = storage.get_order(order.client_order_id)
    assert restored == order


def test_order_status_transitions_are_persisted(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    order = Order(
        client_order_id="cycle-2-eth-buy",
        symbol="KRW-ETH",
        side=OrderSide.BUY,
        status=OrderStatus.CREATED,
        amount_krw=50_000,
    )
    storage.create_order(order)

    submitted = storage.transition_order(order.client_order_id, OrderStatus.SUBMITTED)
    filled = storage.transition_order(order.client_order_id, OrderStatus.FILLED)

    assert submitted.status is OrderStatus.SUBMITTED
    assert filled.status is OrderStatus.FILLED
    assert storage.get_order(order.client_order_id) == filled


def test_terminal_order_status_cannot_transition(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    order = Order(
        client_order_id="cycle-3-xrp-sell",
        symbol="KRW-XRP",
        side=OrderSide.SELL,
        status=OrderStatus.CREATED,
        quantity=10.0,
    )
    storage.create_order(order)
    storage.transition_order(order.client_order_id, OrderStatus.CANCELLED)

    with pytest.raises(ValueError, match="invalid order transition"):
        storage.transition_order(order.client_order_id, OrderStatus.SUBMITTED)


def test_unknown_order_transition_fails_closed(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")

    with pytest.raises(KeyError, match="unknown client_order_id"):
        storage.transition_order("missing-order", OrderStatus.FAILED)
