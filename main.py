from __future__ import annotations

from aipro.app import TradingApplication
from aipro.config import Settings
from aipro.logging_setup import configure_logging


def build_application() -> TradingApplication:
    settings = Settings.from_env()
    configure_logging(settings.log_level, settings.log_dir)
    return TradingApplication(settings)
