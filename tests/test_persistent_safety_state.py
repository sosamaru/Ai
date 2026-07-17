from __future__ import annotations

from datetime import date
from pathlib import Path

from aipro.app import TradingApplication
from aipro.config import Settings
from aipro.storage import Storage


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )


def test_storage_state_survives_reopen(tmp_path: Path) -> None:
    path = tmp_path / "state.db"
    first = Storage(path)
    first.set_state("halted", "1")

    second = Storage(path)

    assert second.get_state("halted") == "1"
    assert second.get_state("missing") is None


def test_daily_baseline_resets_when_kst_date_changes(tmp_path: Path) -> None:
    current_date = [date(2026, 7, 17)]
    app = TradingApplication(
        _settings(tmp_path),
        date_provider=lambda: current_date[0],
    )

    app.run_once()
    assert app.storage.get_state("trading_date") == "2026-07-17"
    assert float(app.storage.get_state("baseline_equity") or 0) == 1_000_000

    app.broker.cash_krw = 900_000
    app.broker.positions.clear()
    current_date[0] = date(2026, 7, 18)
    app.run_once()

    assert app.storage.get_state("trading_date") == "2026-07-18"
    assert float(app.storage.get_state("baseline_equity") or 0) == 900_000


def test_halted_latch_survives_application_restart(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    today = date(2026, 7, 17)
    app = TradingApplication(settings, date_provider=lambda: today)
    app.storage.set_state("trading_date", today.isoformat())
    app.storage.set_state("baseline_equity", "2000000")
    app.baseline_equity = 2_000_000

    app.run_once()

    assert app.risk.halted is True
    assert app.storage.get_state("halted") == "1"

    restarted = TradingApplication(settings, date_provider=lambda: today)

    assert restarted.risk.halted is True
    assert restarted.risk.position_size(1_000_000, 0.4, 5_000) == 0


def test_explicit_resume_clears_latch_and_rebases_equity(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    today = date(2026, 7, 17)
    storage = Storage(settings.db_path)
    storage.set_state("halted", "1")
    storage.set_state("trading_date", today.isoformat())
    storage.set_state("baseline_equity", "2000000")

    app = TradingApplication(settings, date_provider=lambda: today)
    app.resume()

    assert app.risk.halted is False
    assert app.storage.get_state("halted") == "0"
    assert float(app.storage.get_state("baseline_equity") or 0) == 1_000_000
