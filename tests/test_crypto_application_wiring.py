from __future__ import annotations

from aipro.crypto.application import CryptoTradingApplication
from aipro.crypto.broker import PaperBroker
from aipro.crypto.config import Settings
from aipro.crypto.market import DemoMarketData
from aipro.crypto.strategy import MomentumStrategy


def test_crypto_application_owns_runtime_wiring(tmp_path) -> None:
    settings = Settings(
        db_path=tmp_path / "aipro.db",
        log_dir=tmp_path / "logs",
    )

    app = CryptoTradingApplication(settings)

    assert isinstance(app.market, DemoMarketData)
    assert isinstance(app.strategy, MomentumStrategy)
    assert isinstance(app.broker, PaperBroker)
    assert app.settings is settings
