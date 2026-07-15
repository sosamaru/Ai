from dataclasses import dataclass


@dataclass(slots=True)
class RiskManager:
    daily_loss_limit_pct: float
    halted: bool = False

    def evaluate(self, daily_return_pct: float) -> bool:
        if daily_return_pct <= self.daily_loss_limit_pct:
            self.halted = True
        return self.halted

    def position_size(self, cash_krw: float, max_position_pct: float, min_order_krw: int) -> int:
        if self.halted:
            return 0
        amount = int(cash_krw * max_position_pct)
        return amount if amount >= min_order_krw else 0
