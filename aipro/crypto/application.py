from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aipro.app import TradingApplication as LegacyTradingApplication
from aipro.crypto.broker import PaperBroker
from aipro.crypto.config import CryptoSettings
from aipro.crypto.market import DemoMarketData, UpbitMarketData, UpbitPublicClient
from aipro.crypto.strategy import MomentumStrategy
from aipro.risk import RiskManager
from aipro.storage import Storage

KST = ZoneInfo("Asia/Seoul")


class CryptoTradingApplication(LegacyTradingApplication):
    """Crypto-owned runtime assembly with legacy behavior preserved.

    The operational methods remain inherited during the compatibility phase,
    while configuration, market data, strategy, and broker dependencies are
    assembled explicitly from the crypto package.
    """

    def __init__(
        self,
        settings: CryptoSettings,
        date_provider: Callable[[], date] | None = None,
    ) -> None:
        self.settings = settings
        self.storage = Storage(settings.db_path)
        if settings.market_data_provider == "UPBIT":
            self.market = UpbitMarketData(
                symbols=settings.crypto_symbols,
                client=UpbitPublicClient(
                    timeout_sec=settings.market_data_timeout_sec,
                    max_attempts=settings.market_data_max_attempts,
                ),
            )
        else:
            self.market = DemoMarketData()
        self.strategy = MomentumStrategy()
        self.broker = PaperBroker.restore(float(settings.initial_cash_krw), self.storage)
        self._date_provider = date_provider or (lambda: datetime.now(KST).date())

        self._migrate_legacy_crypto_baseline_state()
        persisted_halt = self.storage.get_state("halted") == "1"
        self.risk = RiskManager(settings.daily_loss_limit_pct, halted=persisted_halt)
        self.baseline_equity = self._load_baseline()


TradingApplication = CryptoTradingApplication

__all__ = ["CryptoTradingApplication", "TradingApplication"]
