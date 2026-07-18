from datetime import date

import pytest

from aipro.app import TradingApplication
from aipro.config import Settings


def _create_losing_halted_app(settings: Settings, trading_date: date) -> TradingApplication:
    app = TradingApplication(settings, date_provider=lambda: trading_date)
    app.status()  # Persist the 1,000,000 KRW baseline before creating a loss.
    app.broker.buy("KRW-BTC", 300_000_000.0, 1_000_000)
    app.run_once()
    return app


def test_forced_liquidation_persists_across_restart(tmp_path) -> None:
    settings = Settings(
        initial_cash_krw=1_000_000,
        daily_loss_limit_pct=-10.0,
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )
    trading_date = date(2026, 7, 18)

    app = _create_losing_halted_app(settings, trading_date)

    assert app.risk.halted is True
    assert app.broker.positions == {}
    assert app.broker.cash_krw == pytest.approx(500_000.0)

    restarted = TradingApplication(settings, date_provider=lambda: trading_date)

    assert restarted.risk.halted is True
    assert restarted.broker.positions == {}
    assert restarted.broker.cash_krw == pytest.approx(500_000.0)
    assert restarted.status()["equity_krw"] == pytest.approx(500_000.0)


def test_halted_restart_does_not_create_new_positions(tmp_path) -> None:
    settings = Settings(
        initial_cash_krw=1_000_000,
        daily_loss_limit_pct=-10.0,
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )
    trading_date = date(2026, 7, 18)

    _create_losing_halted_app(settings, trading_date)

    restarted = TradingApplication(settings, date_provider=lambda: trading_date)
    restarted.run_once()

    assert restarted.risk.halted is True
    assert restarted.broker.positions == {}
    assert restarted.broker.cash_krw == pytest.approx(500_000.0)
