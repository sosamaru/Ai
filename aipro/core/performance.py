"""Explicit-unit performance accounting shared by independent market books."""
from __future__ import annotations

from dataclasses import dataclass
import math
from statistics import fmean, stdev
from zoneinfo import ZoneInfo

from aipro.core.evidence import domain as check_domain, finite, instant


@dataclass(frozen=True)
class EquityObservation:
    at: str
    equity: float
    exposure: float = 0.0
    regime: str = "unknown"

    def __post_init__(self):
        instant(self.at)
        finite(self.equity, "equity", 0)
        finite(self.exposure, "exposure", 0, 1)


@dataclass(frozen=True)
class ClosedTrade:
    at: str
    pnl: float
    entry_notional: float
    regime: str = "unknown"
    model_id: str = "unattributed"

    def __post_init__(self):
        instant(self.at)
        finite(self.pnl, "net pnl")
        if finite(self.entry_notional, "entry notional", 0) == 0:
            raise ValueError("positive entry notional including entry fees required")


def trade_summary(trades) -> dict:
    values = [t.pnl for t in trades]
    wins, losses = [v for v in values if v > 0], [v for v in values if v < 0]
    max_wins = max_losses = current_wins = current_losses = 0
    for v in values:
        current_wins = current_wins + 1 if v > 0 else 0
        current_losses = current_losses + 1 if v < 0 else 0
        max_wins, max_losses = max(max_wins, current_wins), max(max_losses, current_losses)
    return {"number_of_trades": len(values), "win_rate": len(wins) / len(values) if values else None,
            "profit_factor": sum(wins) / -sum(losses) if losses else None,
            "average_win": fmean(wins) if wins else None, "average_loss": fmean(losses) if losses else None,
            "expected_value_per_trade": fmean(values) if values else None,
            "mean_net_trade_return": fmean(t.pnl / t.entry_notional for t in trades) if trades else None,
            "maximum_consecutive_wins": max_wins, "maximum_consecutive_losses": max_losses}


def performance_report(observations, trades=(), *, domain: str, fee_cost=0.0, slippage_cost=0.0,
                       turnover_notional=0.0, currency="KRW") -> dict:
    check_domain(domain)
    points, trades = tuple(observations), tuple(trades)
    if not points or points[0].equity <= 0:
        raise ValueError("positive initial equity required")
    times = [instant(p.at) for p in points]
    if any(b <= a for a, b in zip(times, times[1:])):
        raise ValueError("equity observations must be strictly chronological")
    if any(instant(t.at) < times[0] or instant(t.at) > times[-1] for t in trades):
        raise ValueError("trade outside equity observation interval")
    if any(instant(b.at) < instant(a.at) for a, b in zip(trades, trades[1:])):
        raise ValueError("closed trades must be chronological")
    for value in (fee_cost, slippage_cost, turnover_notional):
        finite(value, "cost or turnover", 0)
    peak, drawdown = points[0].equity, 0.0
    daily, monthly = {}, {}
    for p, at in zip(points, times):
        peak = max(peak, p.equity)
        drawdown = max(drawdown, 1 - p.equity / peak)
        date = at.astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
        daily[date] = p.equity
        monthly[date[:7]] = p.equity
    closes = list(daily.values())
    # Adjacent observed KST daily closes; no invented flat weekends or intraday
    # returns annualized as if they were daily returns.
    returns = [b / a - 1 for a, b in zip(closes, closes[1:]) if a > 0]
    periods = 365 if domain == "crypto" else 252
    sharpe = sortino = cagr = calmar = None
    if len(returns) >= 2:
        deviation = stdev(returns)
        downside = math.sqrt(fmean(min(x, 0) ** 2 for x in returns))
        sharpe = fmean(returns) / deviation * math.sqrt(periods) if deviation else None
        sortino = fmean(returns) / downside * math.sqrt(periods) if downside else None
    seconds = (times[-1] - times[0]).total_seconds()
    years = seconds / (365.25 * 86400)
    if seconds >= 30 * 86400:
        try:
            cagr = (points[-1].equity / points[0].equity) ** (1 / years) - 1
        except OverflowError:
            cagr = None
        calmar = cagr / drawdown if cagr is not None and drawdown else None
    exposure = (sum(a.exposure * (tb - ta).total_seconds() for a, ta, tb in
                    zip(points, times, times[1:])) / seconds) if seconds else points[0].exposure
    monthly_returns, prior = {}, points[0].equity
    for month, equity in monthly.items():
        monthly_returns[month] = equity / prior - 1 if prior else None
        prior = equity
    grouped = {}
    for attribute in ("regime", "model_id"):
        grouped[attribute] = {key: trade_summary(tuple(t for t in trades if getattr(t, attribute) == key))
                              for key in sorted({getattr(t, attribute) for t in trades})}
    return {"domain": domain, "currency": currency, "return_units": "fraction", "initial_equity": points[0].equity,
            "final_equity": points[-1].equity, "total_return": points[-1].equity / points[0].equity - 1,
            "cagr": cagr, "sharpe_ratio": sharpe, "sortino_ratio": sortino, "maximum_drawdown": drawdown,
            "calmar_ratio": calmar, **trade_summary(trades), "fee_cost": fee_cost, "slippage_cost": slippage_cost,
            "turnover": turnover_notional / fmean(p.equity for p in points) if any(p.equity for p in points) else None,
            "exposure": exposure, "regime_performance": grouped["regime"], "model_performance": grouped["model_id"],
            "monthly_returns": monthly_returns, "daily_closes": daily, "daily_returns": returns,
            "annualization_periods": periods, "risk_free_rate": 0.0,
            "limitations": ["Ratios use adjacent observed KST daily closes; missing sessions need separate coverage validation.",
                            "CAGR is suppressed below 30 calendar days; undefined ratios are null, not zero or infinity.",
                            "Closed-trade statistics require complete cost-inclusive position episodes, not partial-fill counts."]}
