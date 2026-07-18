import pytest

from aipro.broker import PaperBroker
from aipro.models import OrderStatus
from aipro.storage import Storage


def test_duplicate_buy_order_is_applied_once(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000, storage)

    first = broker.submit_buy("buy-001", "KRW-BTC", 100_000_000.0, 400_000)
    duplicate = broker.submit_buy("buy-001", "KRW-BTC", 90_000_000.0, 300_000)

    assert duplicate == first
    assert broker.cash_krw == pytest.approx(600_000.0)
    assert broker.positions["KRW-BTC"].quantity == pytest.approx(0.004)
    assert len(broker.orders) == 1


def test_duplicate_sell_order_is_applied_once(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000, storage)
    broker.submit_buy("buy-001", "KRW-BTC", 100_000_000.0, 400_000)

    first = broker.submit_sell_all("sell-001", "KRW-BTC", 110_000_000.0)
    cash_after_first_sell = broker.cash_krw
    duplicate = broker.submit_sell_all("sell-001", "KRW-BTC", 120_000_000.0)

    assert first.status is OrderStatus.FILLED
    assert duplicate == first
    assert broker.cash_krw == pytest.approx(cash_after_first_sell)
    assert broker.positions == {}
    assert len(broker.orders) == 2


def test_order_ids_survive_restart(tmp_path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(1_000_000, storage)
    first = broker.submit_buy("buy-restart-001", "KRW-ETH", 5_000_000.0, 250_000)

    restarted = PaperBroker.restore(1_000_000, Storage(tmp_path / "aipro.db"))
    duplicate = restarted.submit_buy(
        "buy-restart-001", "KRW-ETH", 4_000_000.0, 250_000
    )

    assert duplicate == first
    assert restarted.cash_krw == pytest.approx(750_000.0)
    assert restarted.positions["KRW-ETH"].quantity == pytest.approx(0.05)
    assert restarted.get_order("buy-restart-001") == first


def test_no_position_sell_is_idempotently_recorded(tmp_path) -> None:
    broker = PaperBroker.restore(1_000_000, Storage(tmp_path / "aipro.db"))

    first = broker.submit_sell_all("sell-empty-001", "KRW-XRP", 3_000.0)
    duplicate = broker.submit_sell_all("sell-empty-001", "KRW-XRP", 4_000.0)

    assert first.status is OrderStatus.NO_POSITION
    assert duplicate == first
    assert broker.cash_krw == pytest.approx(1_000_000.0)


def test_blank_client_order_id_is_rejected(tmp_path) -> None:
    broker = PaperBroker.restore(1_000_000, Storage(tmp_path / "aipro.db"))

    with pytest.raises(ValueError, match="client_order_id is required"):
        broker.submit_buy("   ", "KRW-BTC", 100_000_000.0, 100_000)
