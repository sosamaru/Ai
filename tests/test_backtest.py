from datetime import datetime, timedelta

import pytest

from aipro.backtest import BacktestBar, BacktestConfig, BacktestEngine
from aipro.models import Decision, Signal


class ScriptedStrategy:
    def decide(self, snapshot):
        if snapshot.change_1h_pct >= 1:
            return Decision(snapshot.symbol, Signal.BUY, 1.0, "scripted buy")
        if snapshot.change_1h_pct <= -1:
            return Decision(snapshot.symbol, Signal.SELL, 1.0, "scripted sell")
        return Decision(snapshot.symbol, Signal.HOLD, 1.0, "scripted hold")


def _bar(offset: int, price: float, change: float, symbol: str = "KRW-BTC") -> BacktestBar:
    return BacktestBar(
        timestamp=datetime(2026, 7, 18, 0, 0) + timedelta(hours=offset),
        symbol=symbol,
        price=price,
        change_1h_pct=change,
        volatility_pct=2.0,
    )


def test_backtest_is_deterministic_and_profitable_when_price_rises() -> None:
    config = BacktestConfig(
        initial_cash_krw=1_000_000,
        max_position_pct=1.0,
        fee_rate=0.0,
        slippage_bps=0.0,
    )
    bars = [_bar(0, 100.0, 1.5), _bar(1, 120.0, 0.0), _bar(2, 120.0, -1.5)]
    engine = BacktestEngine(ScriptedStrategy(), config)

    first = engine.run(bars)
    second = engine.run(reversed(bars))

    assert first == second
    assert first.final_equity_krw == pytest.approx(1_200_000)
    assert first.total_return_pct == pytest.approx(20.0)
    assert first.trade_count == 2
    assert first.closed_trade_count == 1
    assert first.win_rate_pct == pytest.approx(100.0)


def test_fees_and_slippage_reduce_result() -> None:
    bars = [_bar(0, 100.0, 1.5), _bar(1, 100.0, -1.5)]
    frictionless = BacktestEngine(
        ScriptedStrategy(),
        BacktestConfig(max_position_pct=1.0, fee_rate=0.0, slippage_bps=0.0),
    ).run(bars)
    realistic = BacktestEngine(
        ScriptedStrategy(),
        BacktestConfig(max_position_pct=1.0, fee_rate=0.001, slippage_bps=10.0),
    ).run(bars)

    assert frictionless.final_equity_krw == pytest.approx(1_000_000)
    assert realistic.final_equity_krw < frictionless.final_equity_krw
    assert realistic.total_fees_krw > 0


def test_max_drawdown_and_losing_trade_are_reported() -> None:
    config = BacktestConfig(
        initial_cash_krw=1_000_000,
        max_position_pct=1.0,
        fee_rate=0.0,
        slippage_bps=0.0,
    )
    result = BacktestEngine(ScriptedStrategy(), config).run(
        [_bar(0, 100.0, 1.5), _bar(1, 80.0, 0.0), _bar(2, 80.0, -1.5)]
    )

    assert result.final_equity_krw == pytest.approx(800_000)
    assert result.max_drawdown_pct == pytest.approx(-20.0)
    assert result.win_rate_pct == pytest.approx(0.0)
    assert result.trades[-1].realized_pnl_krw == pytest.approx(-200_000)


def test_max_positions_prevents_new_symbol_but_allows_existing_position() -> None:
    config = BacktestConfig(
        initial_cash_krw=1_000_000,
        max_positions=1,
        max_position_pct=0.4,
        fee_rate=0.0,
        slippage_bps=0.0,
    )
    result = BacktestEngine(ScriptedStrategy(), config).run(
        [
            _bar(0, 100.0, 1.5, "KRW-BTC"),
            _bar(0, 50.0, 1.5, "KRW-ETH"),
            _bar(1, 110.0, 1.5, "KRW-BTC"),
        ]
    )

    buys = [trade for trade in result.trades if trade.side == "BUY"]
    assert [trade.symbol for trade in buys] == ["KRW-BTC", "KRW-BTC"]


def test_report_has_machine_and_human_readable_formats() -> None:
    result = BacktestEngine(
        ScriptedStrategy(),
        BacktestConfig(max_position_pct=1.0, fee_rate=0.0, slippage_bps=0.0),
    ).run([_bar(0, 100.0, 1.5), _bar(1, 110.0, -1.5)])

    payload = result.to_dict()
    assert payload["summary"]["total_return_pct"] == pytest.approx(10.0)
    assert payload["trades"][0]["timestamp"] == "2026-07-18T00:00:00"
    assert "AiPro Backtest Report" in result.to_text()
    assert "Total return: 10.0000%" in result.to_text()


def test_empty_data_and_invalid_configuration_are_rejected() -> None:
    with pytest.raises(ValueError, match="at least one bar"):
        BacktestEngine(ScriptedStrategy()).run([])
    with pytest.raises(ValueError, match="price must be positive"):
        _bar(0, 0.0, 1.0)
    with pytest.raises(ValueError, match="max_position_pct"):
        BacktestConfig(max_position_pct=0.0)
