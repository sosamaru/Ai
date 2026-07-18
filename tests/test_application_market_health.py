from __future__ import annotations

import pytest

from aipro.config import Settings
from aipro.crypto.application import CryptoTradingApplication
from aipro.crypto.market_health import MarketDataHealthError


class FailingProvider:
    def snapshots(self):
        raise RuntimeError("provider unavailable")


def test_status_exposes_market_health(tmp_path) -> None:
    app = CryptoTradingApplication(Settings(db_path=tmp_path / "aipro.db"))

    status = app.status()

    assert status["market_data"]["provider"] == "DEMO"
    assert status["market_data"]["healthy"] is True


def test_market_failure_aborts_active_cycle(tmp_path) -> None:
    app = CryptoTradingApplication(Settings(db_path=tmp_path / "aipro.db"))
    app.market = FailingProvider()

    with pytest.raises(MarketDataHealthError, match="provider unavailable"):
        app.run_once()

    assert app.storage.get_state("active_cycle_id") == ""
