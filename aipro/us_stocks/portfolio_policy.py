"""Owner's fixed capital boundary and conservative PAPER policy.

Rates are fractions (0.02 means 2%). None is a promised return or loss bound.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json


EXTERNAL_FUNDING_CAP_KRW = Decimal("1000000")
INITIAL_ALLOCATIONS = {"short": Decimal("200000"), "long": Decimal("800000")}
ZERO = Decimal("0")


def number(value: object, *, minimum: Decimal = ZERO) -> Decimal:
    if isinstance(value, bool):
        raise ValueError("boolean is not a monetary value")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("invalid decimal value") from exc
    if not result.is_finite() or result < minimum:
        raise ValueError("value must be finite and within its allowed range")
    return result


@dataclass(frozen=True, slots=True)
class PortfolioPolicy:
    short_daily_target: Decimal = Decimal("0.02")
    short_daily_loss: Decimal = Decimal("0.01")
    short_max_drawdown: Decimal = Decimal("0.06")
    total_max_drawdown: Decimal = Decimal("0.10")
    short_risk_per_trade: Decimal = Decimal("0.005")
    short_position_fraction: Decimal = Decimal("0.475")
    long_position_fraction: Decimal = Decimal("0.25")
    cash_reserve_fraction: Decimal = Decimal("0.05")
    short_stop: Decimal = Decimal("0.015")
    short_take_profit: Decimal = Decimal("0.03")
    short_trailing_stop: Decimal = Decimal("0.012")
    long_position_stop: Decimal = Decimal("0.12")
    fee_rate: Decimal = Decimal("0.001")
    fx_cost_rate: Decimal = Decimal("0.001")
    slippage_rate: Decimal = Decimal("0.0005")
    max_spread_bps: Decimal = Decimal("25")
    minimum_order_krw: Decimal = Decimal("5000")
    minimum_daily_dollar_volume: Decimal = Decimal("1000000")
    short_max_positions: int = 2
    long_max_positions: int = 4
    short_max_entries_per_day: int = 3
    long_review_days: int = 7
    quote_max_age_seconds: int = 60
    frame_max_age_seconds: int = 60
    intelligence_max_age_seconds: int = 86400
    flatten_before_close_seconds: int = 300
    allow_fractional: bool = False

    def __post_init__(self) -> None:
        for key, value in asdict(self).items():
            if isinstance(value, Decimal):
                number(value)
                if key not in {"max_spread_bps", "minimum_order_krw", "minimum_daily_dollar_volume"}:
                    if value >= 1:
                        raise ValueError(f"{key} must be below 1")
            elif key != "allow_fractional":
                if type(value) is not int or value <= 0:
                    raise ValueError(f"{key} must be a positive integer")
        if type(self.allow_fractional) is not bool:
            raise ValueError("allow_fractional must be boolean")
        for key in ("short_daily_target", "short_daily_loss", "short_max_drawdown",
                    "total_max_drawdown", "short_risk_per_trade", "short_stop",
                    "short_take_profit", "short_trailing_stop", "long_position_stop",
                    "short_position_fraction", "long_position_fraction", "minimum_order_krw"):
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive")
        if self.short_risk_per_trade > self.short_daily_loss:
            raise ValueError("per-trade risk exceeds daily stop")

    @property
    def fingerprint(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True, default=str).encode()).hexdigest()
