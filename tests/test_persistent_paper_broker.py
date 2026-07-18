from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from aipro.app import TradingApplication
from aipro.broker import PaperBroker
from aipro.config import Settings
from aipro.storage import Storage


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )


def test_paper_broker_restores_cash_positions_and_transactions(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "paper.db")
    broker = PaperBroker.restore(storage, 1_000_000)

    broker.buy("KRW-BTC", price=100_000, amount_krw=200_000)

    restarted = PaperBroker.restore(Storage(tmp_path / "paper.db"), 1_000_000)
    assert restarted.cash_krw == pytest.approx(800_000)
    assert restarted.positions["KRW-BTC"].quantity == pytest.approx(2.0)
    assert restarted.positions["KRW-BTC"].average_price == pytest.approx(100_000)

    restarted.sell_all("KRW-BTC", price=110_000)
    final = PaperBroker.restore(Storage(tmp_path / "paper.db"), 1_000_000)

    assert final.cash_krw == pytest.approx(1_020_000)
    assert final.positions == {}
    transactions = storage.list_paper_transactions()
    assert [item["side"] for item in transactions] == ["BUY", "SELL"]
    assert transactions[-1]["cash_after_krw"] == pytest.approx(1_020_000)


def test_application_restart_does_not_reset_simulated_capital(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    today = date(2026, 7, 18)
    first = TradingApplication(settings, date_provider=lambda: today)
    snapshot = first.market.snapshots()[0]

    first.broker.buy(snapshot.symbol, snapshot.price, 250_000)
    restarted = TradingApplication(settings, date_provider=lambda: today)

    assert restarted.broker.cash_krw == pytest.approx(750_000)
    assert snapshot.symbol in restarted.broker.positions
    assert restarted.broker.equity({snapshot.symbol: snapshot.price}) == pytest.approx(1_000_000)


def test_forced_liquidation_is_persisted_across_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    today = date(2026, 7, 18)
    app = TradingApplication(settings, date_provider=lambda: today)
    snapshot = app.market.snapshots()[0]
    app.broker.buy(snapshot.symbol, snapshot.price, 200_000)

    app.storage.set_state("trading_date", today.isoformat())
    app.storage.set_state("baseline_equity", "2000000")
    app.baseline_equity = 2_000_000
    app.run_once()

    assert app.risk.halted is True
    assert app.broker.positions == {}

    restarted = TradingApplication(settings, date_provider=lambda: today)
    assert restarted.risk.halted is True
    assert restarted.broker.positions == {}
    assert restarted.broker.cash_krw == pytest.approx(1_000_000)
    assert [item["side"] for item in restarted.storage.list_paper_transactions()] == [
        "BUY",
        "SELL",
    ]


def test_corrupted_paper_state_fails_closed(tmp_path: Path) -> None:
    storage = Storage(tmp_path / "paper.db")
    with storage._connect() as conn:
        conn.execute("PRAGMA ignore_check_constraints = ON")
        conn.execute(
            "INSERT INTO paper_account(id, cash_krw) VALUES (1, -1)"
        )

    with pytest.raises(ValueError, match="corrupted paper account state"):
        PaperBroker.restore(storage, 1_000_000)
