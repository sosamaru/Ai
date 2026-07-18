from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Protocol

from aipro.models import MarketSnapshot, Signal


class Strategy(Protocol):
    def decide(self, snapshot: MarketSnapshot): ...


@dataclass(frozen=True, slots=True)
class BacktestBar:
    timestamp: datetime
    symbol: str
    price: float
    change_1h_pct: float
    volatility_pct: float

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol is required")
        if self.price <= 0:
            raise ValueError("price must be positive")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_cash_krw: float = 1_000_000.0
    max_positions: int = 2
    max_position_pct: float = 0.40
    min_order_krw: float = 5_000.0
    fee_rate: float = 0.0005
    slippage_bps: float = 10.0

    def __post_init__(self) -> None:
        if self.initial_cash_krw <= 0:
            raise ValueError("initial_cash_krw must be positive")
        if self.max_positions < 1:
            raise ValueError("max_positions must be at least 1")
        if not 0 < self.max_position_pct <= 1:
            raise ValueError("max_position_pct must be in (0, 1]")
        if self.min_order_krw <= 0:
            raise ValueError("min_order_krw must be positive")
        if self.fee_rate < 0:
            raise ValueError("fee_rate must be non-negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps must be non-negative")


@dataclass(frozen=True, slots=True)
class BacktestTrade:
    timestamp: datetime
    symbol: str
    side: str
    execution_price: float
    quantity: float
    gross_krw: float
    fee_krw: float
    realized_pnl_krw: float


@dataclass(frozen=True, slots=True)
class BacktestResult:
    initial_equity_krw: float
    final_equity_krw: float
    total_return_pct: float
    max_drawdown_pct: float
    trade_count: int
    closed_trade_count: int
    win_rate_pct: float
    total_fees_krw: float
    average_exposure_pct: float
    equity_curve: tuple[tuple[datetime, float], ...]
    trades: tuple[BacktestTrade, ...]


@dataclass(slots=True)
class _Position:
    quantity: float
    average_cost: float


class BacktestEngine:
    def __init__(self, strategy: Strategy, config: BacktestConfig | None = None) -> None:
        self.strategy = strategy
        self.config = config or BacktestConfig()

    def run(self, bars: Iterable[BacktestBar]) -> BacktestResult:
        ordered = sorted(bars, key=lambda bar: (bar.timestamp, bar.symbol))
        if not ordered:
            raise ValueError("at least one bar is required")

        cash = self.config.initial_cash_krw
        positions: dict[str, _Position] = {}
        latest_prices: dict[str, float] = {}
        trades: list[BacktestTrade] = []
        equity_curve: list[tuple[datetime, float]] = []
        exposure_samples: list[float] = []
        closed_pnls: list[float] = []
        total_fees = 0.0

        for bar in ordered:
            latest_prices[bar.symbol] = bar.price
            snapshot = MarketSnapshot(
                symbol=bar.symbol,
                price=bar.price,
                change_1h_pct=bar.change_1h_pct,
                volatility_pct=bar.volatility_pct,
            )
            decision = self.strategy.decide(snapshot)

            if decision.signal is Signal.BUY:
                is_new = bar.symbol not in positions
                if not (is_new and len(positions) >= self.config.max_positions):
                    amount = min(cash * self.config.max_position_pct, cash)
                    if amount >= self.config.min_order_krw:
                        execution_price = self._buy_price(bar.price)
                        fee = amount * self.config.fee_rate
                        spendable = amount - fee
                        quantity = spendable / execution_price
                        if quantity > 0:
                            existing = positions.get(bar.symbol)
                            if existing is None:
                                positions[bar.symbol] = _Position(quantity, execution_price)
                            else:
                                total_quantity = existing.quantity + quantity
                                existing.average_cost = (
                                    existing.quantity * existing.average_cost
                                    + quantity * execution_price
                                ) / total_quantity
                                existing.quantity = total_quantity
                            cash -= amount
                            total_fees += fee
                            trades.append(
                                BacktestTrade(
                                    timestamp=bar.timestamp,
                                    symbol=bar.symbol,
                                    side="BUY",
                                    execution_price=execution_price,
                                    quantity=quantity,
                                    gross_krw=amount,
                                    fee_krw=fee,
                                    realized_pnl_krw=0.0,
                                )
                            )

            elif decision.signal is Signal.SELL and bar.symbol in positions:
                position = positions.pop(bar.symbol)
                execution_price = self._sell_price(bar.price)
                gross = position.quantity * execution_price
                fee = gross * self.config.fee_rate
                proceeds = gross - fee
                realized = proceeds - position.quantity * position.average_cost
                cash += proceeds
                total_fees += fee
                closed_pnls.append(realized)
                trades.append(
                    BacktestTrade(
                        timestamp=bar.timestamp,
                        symbol=bar.symbol,
                        side="SELL",
                        execution_price=execution_price,
                        quantity=position.quantity,
                        gross_krw=gross,
                        fee_krw=fee,
                        realized_pnl_krw=realized,
                    )
                )

            equity = cash + sum(
                position.quantity * latest_prices.get(symbol, position.average_cost)
                for symbol, position in positions.items()
            )
            invested = max(0.0, equity - cash)
            equity_curve.append((bar.timestamp, equity))
            exposure_samples.append(0.0 if equity <= 0 else invested / equity * 100)

        final_equity = equity_curve[-1][1]
        total_return = (final_equity / self.config.initial_cash_krw - 1) * 100
        max_drawdown = self._max_drawdown_pct(equity_curve)
        wins = sum(1 for pnl in closed_pnls if pnl > 0)
        win_rate = 0.0 if not closed_pnls else wins / len(closed_pnls) * 100
        average_exposure = sum(exposure_samples) / len(exposure_samples)

        return BacktestResult(
            initial_equity_krw=self.config.initial_cash_krw,
            final_equity_krw=final_equity,
            total_return_pct=total_return,
            max_drawdown_pct=max_drawdown,
            trade_count=len(trades),
            closed_trade_count=len(closed_pnls),
            win_rate_pct=win_rate,
            total_fees_krw=total_fees,
            average_exposure_pct=average_exposure,
            equity_curve=tuple(equity_curve),
            trades=tuple(trades),
        )

    def _buy_price(self, price: float) -> float:
        return price * (1 + self.config.slippage_bps / 10_000)

    def _sell_price(self, price: float) -> float:
        return price * (1 - self.config.slippage_bps / 10_000)

    @staticmethod
    def _max_drawdown_pct(curve: list[tuple[datetime, float]]) -> float:
        peak = curve[0][1]
        max_drawdown = 0.0
        for _, equity in curve:
            peak = max(peak, equity)
            if peak > 0:
                drawdown = (equity / peak - 1) * 100
                max_drawdown = min(max_drawdown, drawdown)
        return max_drawdown
