from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from aipro.app import ACTIVE_CYCLE_STATE_KEY, TradingApplication as LegacyTradingApplication
from aipro.crypto.broker import PaperBroker
from aipro.crypto.config import CryptoSettings
from aipro.crypto.market import DemoMarketData, UpbitMarketData, UpbitPublicClient
from aipro.crypto.market_health import (
    HealthCheckedMarketData,
    MarketDataHealthError,
    MarketDataHealthPolicy,
)
from aipro.crypto.strategy import MomentumStrategy
from aipro.risk import RiskManager
from aipro.storage import Storage

KST = ZoneInfo("Asia/Seoul")


class CryptoTradingApplication(LegacyTradingApplication):
    """Crypto-owned runtime assembly with market-data safety boundaries."""

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
        self.market_health = HealthCheckedMarketData(
            provider_name=settings.market_data_provider,
            delegate=self.market,
            policy=MarketDataHealthPolicy(
                max_latency_sec=settings.market_data_max_latency_sec,
                max_snapshot_age_sec=settings.market_data_max_snapshot_age_sec,
                max_consecutive_failures=settings.market_data_max_consecutive_failures,
            ),
        )
        self.strategy = MomentumStrategy()
        self.broker = PaperBroker.restore(float(settings.initial_cash_krw), self.storage)
        self._date_provider = date_provider or (lambda: datetime.now(KST).date())

        self._migrate_legacy_crypto_baseline_state()
        persisted_halt = self.storage.get_state("halted") == "1"
        self.risk = RiskManager(settings.daily_loss_limit_pct, halted=persisted_halt)
        self.baseline_equity = self._load_baseline()

    def _call_with_health_gate(self, operation: Callable[[], object]) -> object:
        original = self.market
        self.market_health.delegate = original
        self.market = self.market_health  # type: ignore[assignment]
        try:
            return operation()
        finally:
            self.market = original

    def status(self) -> dict[str, object]:
        result = self._call_with_health_gate(super().status)
        assert isinstance(result, dict)
        result["market_data"] = self.market_health.health_status()
        return result

    def run_once(self) -> None:
        try:
            self._call_with_health_gate(super().run_once)
        except MarketDataHealthError as exc:
            cycle_id = self.storage.get_state(ACTIVE_CYCLE_STATE_KEY)
            if cycle_id:
                self.storage.set_state(ACTIVE_CYCLE_STATE_KEY, "")
                self.storage.record(
                    "cycle_aborted_market_data",
                    json.dumps(
                        {
                            "cycle_id": cycle_id,
                            "provider": self.settings.market_data_provider,
                            "reason": str(exc),
                        },
                        sort_keys=True,
                    ),
                )
            raise


TradingApplication = CryptoTradingApplication

__all__ = ["CryptoTradingApplication", "TradingApplication"]
