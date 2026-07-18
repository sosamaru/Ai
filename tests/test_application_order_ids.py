from datetime import date

import pytest

from aipro.app import ACTIVE_CYCLE_STATE_KEY, TradingApplication
from aipro.config import Settings
from aipro.models import OrderSide


def _settings(tmp_path) -> Settings:
    return Settings(
        initial_cash_krw=1_000_000,
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )


def test_successive_cycles_generate_distinct_deterministic_order_ids(tmp_path) -> None:
    settings = _settings(tmp_path)
    trading_date = date(2026, 7, 18)
    app = TradingApplication(settings, date_provider=lambda: trading_date)

    app.run_once()
    app.run_once()

    buy_orders = [
        order for order in app.broker.orders.values() if order.side is OrderSide.BUY
    ]
    assert len(buy_orders) == 2
    assert {order.client_order_id for order in buy_orders} == {
        "paper:2026-07-18-00000001:buy:KRW-BTC",
        "paper:2026-07-18-00000002:buy:KRW-BTC",
    }
    assert app.status()["cycle_sequence"] == 2
    assert app.status()["active_cycle_id"] is None


def test_interrupted_cycle_reuses_order_ids_after_restart(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)
    trading_date = date(2026, 7, 18)
    app = TradingApplication(settings, date_provider=lambda: trading_date)
    original_submit_sell = app.broker.submit_sell_all

    def fail_after_buy(client_order_id: str, symbol: str, price: float):
        raise RuntimeError("simulated process interruption")

    monkeypatch.setattr(app.broker, "submit_sell_all", fail_after_buy)

    with pytest.raises(RuntimeError, match="simulated process interruption"):
        app.run_once()

    cash_after_interruption = app.broker.cash_krw
    assert cash_after_interruption == pytest.approx(600_000.0)
    assert app.storage.get_state(ACTIVE_CYCLE_STATE_KEY) == "2026-07-18-00000001"
    assert len([o for o in app.broker.orders.values() if o.side is OrderSide.BUY]) == 1

    # A new process restores both the active cycle and the already-filled buy order.
    restarted = TradingApplication(settings, date_provider=lambda: trading_date)
    restarted.run_once()

    buy_orders = [
        order for order in restarted.broker.orders.values() if order.side is OrderSide.BUY
    ]
    assert len(buy_orders) == 1
    assert buy_orders[0].client_order_id == "paper:2026-07-18-00000001:buy:KRW-BTC"
    assert restarted.broker.cash_krw == pytest.approx(cash_after_interruption)
    assert restarted.status()["active_cycle_id"] is None
    assert restarted.status()["cycle_sequence"] == 1


def test_order_id_normalizes_symbol_and_rejects_empty_symbol() -> None:
    assert (
        TradingApplication._order_id("2026-07-18-00000001", "buy", "krw/btc")
        == "paper:2026-07-18-00000001:buy:KRW-BTC"
    )
    with pytest.raises(ValueError, match="symbol is required"):
        TradingApplication._order_id("2026-07-18-00000001", "buy", "   ")
