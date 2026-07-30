from __future__ import annotations

from threading import Event, Thread

import pytest

from aipro.config import Settings
from aipro.crypto.application import CryptoTradingApplication
from aipro.crypto.market import DemoMarketData
from aipro.crypto.market_health import MarketDataHealthError


class FailingProvider:
    def snapshots(self):
        raise RuntimeError("provider unavailable")


class BlockingProvider:
    def __init__(self) -> None:
        self.started = Event()
        self.release = Event()
        self.delegate = DemoMarketData()
        self.calls = 0

    def snapshots(self):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            if not self.release.wait(timeout=2):
                raise RuntimeError("test provider release timed out")
        return self.delegate.snapshots()


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


def test_concurrent_health_checked_calls_are_serialized(tmp_path) -> None:
    app = CryptoTradingApplication(Settings(db_path=tmp_path / "aipro.db"))
    provider = BlockingProvider()
    app.market = provider
    results: list[dict[str, object]] = []
    errors: list[BaseException] = []
    second_finished = Event()

    def call_status(*, mark_finished: bool = False) -> None:
        try:
            results.append(app.status())
        except BaseException as exc:  # pragma: no cover - asserted below
            errors.append(exc)
        finally:
            if mark_finished:
                second_finished.set()

    first = Thread(target=call_status)
    first.start()
    assert provider.started.wait(timeout=1)

    second = Thread(target=call_status, kwargs={"mark_finished": True})
    second.start()
    assert not second_finished.wait(timeout=0.1)

    provider.release.set()
    first.join(timeout=2)
    second.join(timeout=2)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(results) == 2
    assert app.market is provider
