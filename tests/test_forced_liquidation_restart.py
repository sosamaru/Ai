from datetime import date

import pytest

from aipro.app import TradingApplication
from aipro.config import Settings


INITIAL_CASH_KRW = 1_000_000
ENTRY_PRICE = 300_000_000.0
LIQUIDATION_PRICE = 150_000_000.0
EXPECTED_CASH_AFTER_LIQUIDATION = (
    INITIAL_CASH_KRW / ENTRY_PRICE
) * LIQUIDATION_PRICE


def _create_losing_halted_app(settings: Settings, trading_date: date) -> TradingApplication:
    app = TradingApplication(settings, date_provider=lambda: trading_date)

    initial_status = app.status()
    assert initial_status["baseline_equity_krw"] == pytest.approx(INITIAL_CASH_KRW)

    app.broker.buy("KRW-BTC", ENTRY_PRICE, INITIAL_CASH_KRW)
    assert "KRW-BTC" in app.broker.positions

    app.run_once()
    return app


def _assert_liquidated_halted_state(app: TradingApplication) -> None:
    assert app.risk.halted is True
    assert app.broker.positions == {}
    assert app.broker.cash_krw == pytest.approx(EXPECTED_CASH_AFTER_LIQUIDATION)


def test_forced_liquidation_persists_across_restart(tmp_path) -> None:
    settings = Settings(
        initial_cash_krw=INITIAL_CASH_KRW,
        daily_loss_limit_pct=-10.0,
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )
    trading_date = date(2026, 7, 18)

    app = _create_losing_halted_app(settings, trading_date)
    _assert_liquidated_halted_state(app)

    restarted = TradingApplication(settings, date_provider=lambda: trading_date)
    _assert_liquidated_halted_state(restarted)

    restarted_status = restarted.status()
    assert restarted_status["halted"] is True
    assert restarted_status["positions"] == 0
    assert restarted_status["equity_krw"] == pytest.approx(
        EXPECTED_CASH_AFTER_LIQUIDATION
    )


def test_halted_restart_does_not_create_new_positions(tmp_path) -> None:
    settings = Settings(
        initial_cash_krw=INITIAL_CASH_KRW,
        daily_loss_limit_pct=-10.0,
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )
    trading_date = date(2026, 7, 18)

    _create_losing_halted_app(settings, trading_date)

    restarted = TradingApplication(settings, date_provider=lambda: trading_date)
    _assert_liquidated_halted_state(restarted)

    restarted.run_once()

    _assert_liquidated_halted_state(restarted)
