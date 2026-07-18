from __future__ import annotations

import json

from aipro.crypto.broker import PaperBroker
from aipro.reconciliation import reconcile_paper_account
from aipro.storage import Storage


def test_completed_orders_archive_without_losing_idempotency(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000.0, storage)

    first = broker.submit_buy("order-1", "KRW-BTC", 100_000.0, 100_000)
    broker.submit_sell_all("order-2", "KRW-BTC", 110_000.0)
    broker.submit_buy("order-3", "KRW-ETH", 50_000.0, 100_000)

    archived = broker.archive_completed_orders(retain_latest=1)

    assert archived == 2
    assert set(broker.orders) == {"order-3"}
    assert broker.get_order("order-1") == first

    cash_before = broker.cash_krw
    duplicate = broker.submit_buy("order-1", "KRW-BTC", 1.0, 1)
    assert duplicate == first
    assert broker.cash_krw == cash_before


def test_reconciliation_uses_active_and_archived_orders(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000.0, storage)
    broker.submit_buy("order-1", "KRW-BTC", 100_000.0, 100_000)
    broker.submit_sell_all("order-2", "KRW-BTC", 110_000.0)
    broker.submit_buy("order-3", "KRW-ETH", 50_000.0, 100_000)

    assert broker.archive_completed_orders(retain_latest=1) == 2
    report = reconcile_paper_account(broker, 1_000_000.0)

    assert report.is_consistent is True


def test_archive_survives_restart_and_is_immutable(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000.0, storage)
    original = broker.submit_buy("order-1", "KRW-BTC", 100_000.0, 100_000)
    broker.submit_sell_all("order-2", "KRW-BTC", 110_000.0)
    assert broker.archive_completed_orders(retain_latest=0) == 2

    restored = PaperBroker.restore(1_000_000.0, storage)
    assert restored.get_order("order-1") == original

    raw = storage.get_archived_paper_order("order-1")
    assert raw is not None
    changed = json.dumps({**json.loads(raw), "amount_krw": 1.0}, sort_keys=True, separators=(",", ":"))

    try:
        storage.archive_paper_order("order-1", changed)
    except ValueError as exc:
        assert "immutable" in str(exc)
    else:
        raise AssertionError("archive overwrite must be rejected")


def test_pending_order_is_never_archived(tmp_path) -> None:
    from aipro.models import OrderRecord, OrderSide, OrderStatus

    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000.0, storage)
    broker.orders["pending-1"] = OrderRecord(
        client_order_id="pending-1",
        side=OrderSide.BUY,
        symbol="KRW-BTC",
        status=OrderStatus.PENDING,
        price=100_000.0,
        quantity=0.0,
        amount_krw=100_000.0,
    )
    broker._persist("test_pending_order")

    assert broker.archive_completed_orders(retain_latest=0) == 0
    assert "pending-1" in broker.orders


def test_retention_argument_validation(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000.0, storage)

    try:
        broker.archive_completed_orders(retain_latest=-1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:
        raise AssertionError("negative retention must be rejected")
