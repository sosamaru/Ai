from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _parse_chat_ids(raw: str) -> frozenset[int]:
    if not raw.strip():
        return frozenset()
    try:
        return frozenset(int(item.strip()) for item in raw.split(",") if item.strip())
    except ValueError as exc:
        raise ValueError("AIPRO_TELEGRAM_ALLOWED_CHAT_IDS must contain integers") from exc


def _parse_symbols(raw: str) -> tuple[str, ...]:
    symbols = tuple(item.strip().upper() for item in raw.split(",") if item.strip())
    if not symbols:
        raise ValueError("AIPRO_CRYPTO_SYMBOLS must contain at least one symbol")
    if len(set(symbols)) != len(symbols):
        raise ValueError("AIPRO_CRYPTO_SYMBOLS must not contain duplicates")
    return symbols


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
    telegram_bot_token: str = ""
    telegram_allowed_chat_ids: frozenset[int] = frozenset()
    telegram_poll_timeout_sec: int = 25
    market_data_provider: str = "DEMO"
    crypto_symbols: tuple[str, ...] = ("KRW-BTC", "KRW-ETH", "KRW-XRP")
    market_data_timeout_sec: float = 5.0
    market_data_max_attempts: int = 3

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
            telegram_bot_token=os.getenv("AIPRO_TELEGRAM_BOT_TOKEN", "").strip(),
            telegram_allowed_chat_ids=_parse_chat_ids(
                os.getenv("AIPRO_TELEGRAM_ALLOWED_CHAT_IDS", "")
            ),
            telegram_poll_timeout_sec=int(
                os.getenv("AIPRO_TELEGRAM_POLL_TIMEOUT_SEC", "25")
            ),
            market_data_provider=os.getenv("AIPRO_MARKET_DATA_PROVIDER", "DEMO").upper(),
            crypto_symbols=_parse_symbols(
                os.getenv("AIPRO_CRYPTO_SYMBOLS", "KRW-BTC,KRW-ETH,KRW-XRP")
            ),
            market_data_timeout_sec=float(
                os.getenv("AIPRO_MARKET_DATA_TIMEOUT_SEC", "5.0")
            ),
            market_data_max_attempts=int(
                os.getenv("AIPRO_MARKET_DATA_MAX_ATTEMPTS", "3")
            ),
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
        if not 1 <= self.telegram_poll_timeout_sec <= 50:
            raise ValueError("telegram_poll_timeout_sec must be between 1 and 50")
        if self.market_data_provider not in {"DEMO", "UPBIT"}:
            raise ValueError("AIPRO_MARKET_DATA_PROVIDER must be DEMO or UPBIT")
        if not self.crypto_symbols:
            raise ValueError("crypto_symbols must not be empty")
        if len(set(self.crypto_symbols)) != len(self.crypto_symbols):
            raise ValueError("crypto_symbols must not contain duplicates")
        if any(not symbol.startswith("KRW-") for symbol in self.crypto_symbols):
            raise ValueError("crypto_symbols currently support KRW Upbit pairs only")
        if self.market_data_timeout_sec <= 0:
            raise ValueError("market_data_timeout_sec must be positive")
        if not 1 <= self.market_data_max_attempts <= 5:
            raise ValueError("market_data_max_attempts must be between 1 and 5")
        if self.telegram_bot_token and not self.telegram_allowed_chat_ids:
            raise RuntimeError(
                "Telegram blocked: configure AIPRO_TELEGRAM_ALLOWED_CHAT_IDS"
            )
        if self.mode == "LIVE" and not (
            self.live_confirm == "YES" and self.enable_live_trading
        ):
            raise RuntimeError(
                "LIVE blocked: set AIPRO_LIVE_CONFIRM=YES and ENABLE_LIVE_TRADING=1"
            )
