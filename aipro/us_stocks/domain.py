from __future__ import annotations

from dataclasses import dataclass

from aipro.core import AssetClass, TradingDomain


US_STOCK_DOMAIN = TradingDomain(
    asset_class=AssetClass.US_STOCK,
    currency="USD",
    enabled=False,
    live_order_submission_enabled=False,
)


@dataclass(frozen=True, slots=True)
class USStockCapitalPolicy:
    """Isolated capital allocation for the future US momentum strategy."""

    budget_krw: int = 200_000
    reserve_pct: float = 0.05
    max_positions: int = 3

    def __post_init__(self) -> None:
        if self.budget_krw <= 0:
            raise ValueError("budget_krw must be positive")
        if not 0 <= self.reserve_pct < 1:
            raise ValueError("reserve_pct must be in [0, 1)")
        if self.max_positions < 1:
            raise ValueError("max_positions must be at least 1")

    @property
    def maximum_deployable_krw(self) -> int:
        return int(self.budget_krw * (1 - self.reserve_pct))
