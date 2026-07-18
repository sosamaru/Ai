from pathlib import Path

import pytest

from aipro.broker import PAPER_ACCOUNT_STATE_KEY, PaperBroker
from aipro.storage import Storage


def test_paper_account_survives_restart(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(100_000, storage)

    broker.buy("KRW-BTC", price=50_000, amount_krw=20_000)

    restored = PaperBroker.restore(100_000, Storage(tmp_path / "aipro.db"))
    assert restored.cash_krw == pytest.approx(80_000)
    assert restored.positions["KRW-BTC"].quantity == pytest.approx(0.4)
    assert restored.positions["KRW-BTC"].average_price == pytest.approx(50_000)


def test_sell_all_is_persisted(tmp_path: Path) -> None:
    db_path = tmp_path / "aipro.db"
    storage = Storage(db_path)
    broker = PaperBroker.restore(100_000, storage)
    broker.buy("KRW-BTC", price=50_000, amount_krw=20_000)

    proceeds = broker.sell_all("KRW-BTC", price=55_000)

    restored = PaperBroker.restore(100_000, Storage(db_path))
    assert proceeds == pytest.approx(22_000)
    assert restored.cash_krw == pytest.approx(102_000)
    assert restored.positions == {}


def test_corrupted_account_state_fails_closed_to_initial_cash(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    storage.set_state(PAPER_ACCOUNT_STATE_KEY, '{"cash_krw":-1,"positions":{}}')

    restored = PaperBroker.restore(100_000, storage)

    assert restored.cash_krw == pytest.approx(100_000)
    assert restored.positions == {}
    persisted = storage.get_state(PAPER_ACCOUNT_STATE_KEY)
    assert persisted is not None
    assert '"cash_krw":100000.0' in persisted


def test_invalid_trade_does_not_change_persisted_state(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "aipro.db")
    broker = PaperBroker.restore(100_000, storage)
    before = storage.get_state(PAPER_ACCOUNT_STATE_KEY)

    with pytest.raises(ValueError):
        broker.buy("KRW-BTC", price=0, amount_krw=20_000)

    assert storage.get_state(PAPER_ACCOUNT_STATE_KEY) == before
