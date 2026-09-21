from dataclasses import dataclass
import math


@dataclass(slots=True)
class RiskManager:
    daily_loss_limit_pct: float
    halted: bool = False

    def __post_init__(self) -> None:
        if not math.isfinite(self.daily_loss_limit_pct) or not -100 <= self.daily_loss_limit_pct < 0:
            raise ValueError("daily loss limit must be finite and in [-100, 0)")
        if type(self.halted) is not bool:
            raise ValueError("halted must be boolean")

    def evaluate(self, daily_return_pct: float) -> bool:
        if isinstance(daily_return_pct, bool) or not math.isfinite(daily_return_pct):
            self.halted = True
            return True
        if daily_return_pct <= self.daily_loss_limit_pct:
            self.halted = True
        return self.halted

    def halt(self) -> None:
        self.halted = True

    def resume(self) -> None:
        self.halted = False

    def position_size(
        self,
        cash_krw: float,
        max_position_pct: float,
        min_order_krw: int,
    ) -> int:
        if self.halted:
            return 0
        amount = int(cash_krw * max_position_pct)
        return amount if amount >= min_order_krw else 0
