from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class AssetClass(StrEnum):
    CRYPTO = "crypto"
    US_STOCK = "us_stock"


@dataclass(frozen=True, slots=True)
class TradingDomain:
    """Declares the ownership boundary for one independently funded trading domain."""

    asset_class: AssetClass
    currency: str
    enabled: bool
    live_order_submission_enabled: bool = False

    def __post_init__(self) -> None:
        if not self.currency.strip():
            raise ValueError("currency is required")
        if self.live_order_submission_enabled and not self.enabled:
            raise ValueError("disabled domains cannot submit live orders")
