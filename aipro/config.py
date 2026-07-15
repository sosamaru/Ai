from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Settings:
    mode: str = "PAPER"
    initial_cash_krw: int = 1_000_000
    max_positions: int = 2
    max_position_pct: float = 0.40
    daily_loss_limit_pct: float = -10.0
    min_order_krw: int = 5_000
    db_path: Path = Path("data/aipro.db")
    log_dir: Path = Path("logs")
    log_level: str = "INFO"
    live_confirm: str = "NO"
    enable_live_trading: bool = False

    @classmethod
    def from_env(cls) -> "Settings":
        settings = cls(
            mode=os.getenv("AIPRO_MODE", "PAPER").upper(),
            initial_cash_krw=int(os.getenv("AIPRO_INITIAL_CASH_KRW", "1000000")),
            max_positions=int(os.getenv("AIPRO_MAX_POSITIONS", "2")),
            max_position_pct=float(os.getenv("AIPRO_MAX_POSITION_PCT", "0.40")),
            daily_loss_limit_pct=float(os.getenv("AIPRO_DAILY_LOSS_LIMIT_PCT", "-10.0")),
            min_order_krw=int(os.getenv("AIPRO_MIN_ORDER_KRW", "5000")),
            db_path=Path(os.getenv("AIPRO_DB_PATH", "data/aipro.db")),
            log_dir=Path(os.getenv("AIPRO_LOG_DIR", "logs")),
            log_level=os.getenv("AIPRO_LOG_LEVEL", "INFO").upper(),
            live_confirm=os.getenv("AIPRO_LIVE_CONFIRM", "NO").upper(),
            enable_live_trading=os.getenv("ENABLE_LIVE_TRADING", "0") == "1",
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if self.mode not in {"PAPER", "LIVE"}:
            raise ValueError("AIPRO_MODE must be PAPER or LIVE")
        if self.max_positions < 1:
            raise ValueError("max_positions must be at least 1")
        if not 0 < self.max_position_pct <= 1:
            raise ValueError("max_position_pct must be in (0, 1]")
        if self.daily_loss_limit_pct >= 0:
            raise ValueError("daily_loss_limit_pct must be negative")
        if self.mode == "LIVE" and not (self.live_confirm == "YES" and self.enable_live_trading):
            raise RuntimeError("LIVE blocked: set AIPRO_LIVE_CONFIRM=YES and ENABLE_LIVE_TRADING=1")
