import pytest

from aipro.backtest import run_backtest
from aipro.broker import PaperBroker
from aipro.execution import OrderGuard
from aipro.models import MarketSnapshot
from aipro.performance import build_performance_report


def test_paper_broker_applies_fee_and_slippage():
    broker = PaperBroker(100_000, fee_rate=0.001, slippage_bps=10)
    fill = broker.buy("KRW-BTC", 10_000, 50_000)
    assert fill.fee_krw == pytest.approx(50)
    assert fill.price == pytest.approx(10_010)
    assert broker.cash_krw == pytest.approx(50_000)
    assert broker.equity({"KRW-BTC": 10_000}) < 100_000


def test_sell_all_closes_position_and_records_fill():
    broker = PaperBroker(100_000, fee_rate=0, slippage_bps=0)
    broker.buy("KRW-BTC", 10_000, 50_000)
    fill = broker.sell_all("KRW-BTC", 11_000)
    assert fill is not None
    assert "KRW-BTC" not in broker.positions
    assert broker.cash_krw == pytest.approx(105_000)
    assert len(broker.fills) == 2


def test_duplicate_order_guard_blocks_within_ttl():
    guard = OrderGuard(ttl_seconds=180)
    assert guard.allow("KRW-BTC", "BUY", now=100)
    assert not guard.allow("KRW-BTC", "BUY", now=200)
    assert guard.allow("KRW-BTC", "BUY", now=281)
    assert guard.allow("KRW-BTC", "SELL", now=282)


def test_performance_report_calculates_drawdown():
    report = build_performance_report([100, 110, 99, 120])
    assert report.total_return_pct == pytest.approx(20)
    assert report.max_drawdown_pct == pytest.approx(-10)
    assert report.winning_periods == 2
    assert report.losing_periods == 1


def test_backtest_runs_without_external_api():
    snapshots = [
        MarketSnapshot("KRW-BTC", 100.0, 1.2, 2.0),
        MarketSnapshot("KRW-BTC", 110.0, 0.2, 2.0),
        MarketSnapshot("KRW-BTC", 115.0, -1.2, 2.0),
    ]
    result = run_backtest(snapshots, initial_cash_krw=100_000)
    assert result.fills == 2
    assert result.final_equity_krw > 100_000
    assert not result.halted
