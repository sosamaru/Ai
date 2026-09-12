from __future__ import annotations

from aipro.crypto.application import TradingApplication
from aipro.crypto.config import Settings
from aipro.logging_setup import configure_logging


def build_application() -> TradingApplication:
    settings = Settings.from_env()
    configure_logging(settings.log_level, settings.log_dir)
    if settings.runtime == "US_DUAL":
        from aipro.us_stocks.portfolio_application import TradingApplication as USPortfolioApplication
        return USPortfolioApplication(settings)
    return TradingApplication(settings)
