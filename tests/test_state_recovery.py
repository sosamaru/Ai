from pathlib import Path

import pytest

from aipro.broker import PaperBroker
from aipro.storage import Storage


def test_paper_broker_round_trip() -> None:
    broker = PaperBroker(100_000.0)
    broker.buy("KRW-BTC", 50_000.0, 20_000)

    restored = PaperBroker.from_dict(broker.to_dict())

    assert restored.cash_krw == pytest.approx(80_000.0)
    assert restored.positions["KRW-BTC"].quantity == pytest.approx(0.4)
    assert restored.positions["KRW-BTC"].average_price == pytest.approx(50_000.0)


def test_storage_persists_runtime_state(tmp_path: Path) -> None:
    database = tmp_path / "state.db"
    first = Storage(database)
    first.save_state(
        "trading_application",
        {
            "version": 1,
            "baseline_equity": 100_000.0,
            "halted": True,
            "broker": {"cash_krw": 80_000.0, "positions": {}},
        },
    )

    second = Storage(database)
    state = second.load_state("trading_application")

    assert state is not None
    assert state["halted"] is True
    assert state["broker"]["cash_krw"] == pytest.approx(80_000.0)


def test_storage_upserts_single_state_record(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "state.db")
    storage.save_state("runtime", {"sequence": 1})
    storage.save_state("runtime", {"sequence": 2})

    assert storage.load_state("runtime") == {"sequence": 2}


def test_broker_rejects_invalid_price() -> None:
    broker = PaperBroker(100_000.0)

    with pytest.raises(ValueError, match="price must be positive"):
        broker.buy("KRW-BTC", 0.0, 10_000)
