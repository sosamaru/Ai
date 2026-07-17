from aipro.app import TradingApplication
from aipro.broker import PaperBroker
from aipro.config import Settings
from aipro.controller import AppMode, Controller
from aipro.storage import Storage


def make_settings(tmp_path):
    return Settings(db_path=tmp_path / "aipro.db", log_dir=tmp_path / "logs")


def test_controller_transitions_and_halt_latch():
    controller = Controller()
    assert controller.can_trade
    controller.pause()
    assert controller.mode is AppMode.PAUSED
    controller.resume()
    assert controller.mode is AppMode.RUNNING
    controller.halt()
    controller.resume()
    assert controller.mode is AppMode.HALTED
    controller.go()
    assert controller.mode is AppMode.RUNNING


def test_storage_round_trip(tmp_path):
    storage = Storage(tmp_path / "state.db")
    storage.save_state("sample", {"value": 3, "nested": {"ok": True}})
    assert storage.load_state("sample") == {"value": 3, "nested": {"ok": True}}


def test_broker_snapshot_restore():
    broker = PaperBroker(100_000)
    broker.buy("KRW-BTC", 10_000, 20_000)
    restored = PaperBroker.restore(broker.snapshot())
    assert restored.cash_krw == broker.cash_krw
    assert restored.positions["KRW-BTC"].quantity == broker.positions["KRW-BTC"].quantity


def test_application_restores_state(tmp_path):
    settings = make_settings(tmp_path)
    first = TradingApplication(settings)
    first.broker.buy("KRW-BTC", 10_000, 20_000)
    first.pause()

    second = TradingApplication(settings)
    assert second.controller.mode is AppMode.PAUSED
    assert "KRW-BTC" in second.broker.positions
    assert second.broker.cash_krw == 980_000


def test_paused_application_skips_cycle(tmp_path):
    app = TradingApplication(make_settings(tmp_path))
    app.pause()
    before = app.broker.cash_krw
    app.run_once()
    assert app.broker.cash_krw == before
    assert app.storage.count_events("cycle_skipped") == 1
