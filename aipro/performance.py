from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    total_return_pct: float
    max_drawdown_pct: float
    winning_periods: int
    losing_periods: int


def build_performance_report(equity_curve: list[float]) -> PerformanceReport:
    if not equity_curve or equity_curve[0] <= 0:
        raise ValueError("equity curve must start with a positive value")

    peak = equity_curve[0]
    max_drawdown = 0.0
    winning_periods = 0
    losing_periods = 0

    for previous, current in zip(equity_curve, equity_curve[1:]):
        if current > previous:
            winning_periods += 1
        elif current < previous:
            losing_periods += 1
        peak = max(peak, current)
        drawdown = (current / peak - 1) * 100
        max_drawdown = min(max_drawdown, drawdown)

    total_return = (equity_curve[-1] / equity_curve[0] - 1) * 100
    return PerformanceReport(total_return, max_drawdown, winning_periods, losing_periods)
