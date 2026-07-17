from __future__ import annotations

from dataclasses import dataclass

from aipro.broker import PaperBroker
from aipro.models import MarketSnapshot, Signal
from aipro.performance import PerformanceReport, build_performance_report
from aipro.risk import RiskManager
from aipro.strategy import MomentumStrategy


@dataclass(frozen=True, slots=True)
class BacktestResult:
    report: PerformanceReport
    final_equity_krw: float
    fills: int
    halted: bool


def run_backtest(
    snapshots: list[MarketSnapshot],
    initial_cash_krw: int = 1_000_000,
    max_position_pct: float = 0.40,
    min_order_krw: int = 5_000,
    daily_loss_limit_pct: float = -10.0,
) -> BacktestResult:
    broker = PaperBroker(float(initial_cash_krw))
    strategy = MomentumStrategy()
    risk = RiskManager(daily_loss_limit_pct)
    equity_curve = [float(initial_cash_krw)]
    last_prices: dict[str, float] = {}

    for snapshot in snapshots:
        last_prices[snapshot.symbol] = snapshot.price
        equity = broker.equity(last_prices)
        return_pct = (equity / initial_cash_krw - 1) * 100
        if risk.evaluate(return_pct):
            for symbol in list(broker.positions):
                broker.sell_all(symbol, last_prices[symbol])
            equity_curve.append(broker.equity(last_prices))
            break

        decision = strategy.decide(snapshot)
        if decision.signal is Signal.BUY and snapshot.symbol not in broker.positions:
            amount = risk.position_size(broker.cash_krw, max_position_pct, min_order_krw)
            if amount:
                broker.buy(snapshot.symbol, snapshot.price, amount)
        elif decision.signal is Signal.SELL:
            broker.sell_all(snapshot.symbol, snapshot.price)
        equity_curve.append(broker.equity(last_prices))

    return BacktestResult(
        report=build_performance_report(equity_curve),
        final_equity_krw=equity_curve[-1],
        fills=len(broker.fills),
        halted=risk.halted,
    )
