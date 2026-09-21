from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal as D

import pytest

from aipro.config import Settings
from aipro.core.adaptive_risk import RiskMode
from aipro.core.runtime_monitor import record_outcome
from aipro.crypto.application import TradingApplication as CryptoApplication
from aipro.crypto.market_health import MarketDataHealthError
from aipro.us_stocks.portfolio_application import TradingApplication
from aipro.us_stocks.portfolio_replay import demo_frame, demo_frames, replay
from aipro.us_stocks.performance_reporting import finalize_daily_reports, reports_from_cycles

START = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)


def test_negative_ev_blocks_entries_but_preserves_existing_risk_exits(tmp_path):
    now = [START]
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: now[0])
    first = app.process_frame(demo_frame(START))
    with app.ledger.transaction() as (db, state):
        monitor = state["monitors"]["short"]
        for i in range(60):
            monitor = record_outcome(monitor, trade_id=str(i), net_return=-.001)
        state["monitors"]["short"] = monitor
    now[0] += timedelta(minutes=1)
    result = app.process_frame(demo_frame(now[0], short_price="10.80"))
    assert any(f["side"] == "SELL" and f["sleeve"] == "short" for f in result["fills"])
    assert not any(f["side"] == "BUY" and f["sleeve"] == "short" for f in result["fills"])
    assert app.ledger.read()["monitors"]["short"]["health"]["mode"] == RiskMode.PAPER_ONLY
    restored = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: now[0])
    assert restored.ledger.read()["monitors"]["short"]["closed_count"] == 61
    with pytest.raises(ValueError, match="EV"):
        restored.resume()


def test_us_api_failure_latches_and_recovery_does_not_auto_resume(tmp_path):
    class Provider:
        def frame(self):
            raise TimeoutError("secret must not appear")
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", market=Provider(), clock=lambda: START)
    for _ in range(3):
        result = app.run_once()
        assert "secret" not in str(result)
    assert app.status()["global_halt"] == "persistent_data_source_failure"
    result = app.process_frame(demo_frame(START))
    assert not any(f["side"] == "BUY" for f in result["fills"])
    assert app.ledger.read()["global_halt"]


def test_crypto_api_failure_halt_survives_restart(tmp_path):
    settings = Settings(db_path=tmp_path / "crypto.db", log_dir=tmp_path / "logs")
    app = CryptoApplication(settings)
    class Broken:
        def snapshots(self):
            raise TimeoutError("offline")
    app.market = Broken()
    for _ in range(3):
        with pytest.raises(MarketDataHealthError):
            app.run_once()
    assert CryptoApplication(settings).risk.halted


def test_replay_produces_full_separate_reports_and_partial_fill_is_one_episode(tmp_path):
    now = [START]
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: now[0])
    cycles = [app.process_frame(demo_frame(now[0]))]
    now[0] += timedelta(minutes=1)
    frame = demo_frame(now[0], short_price="9.60")
    partial = replace(frame, quotes=(replace(frame.quotes[0], bid_size=D(1)), frame.quotes[1]))
    cycles.append(app.process_frame(partial))
    assert cycles[-1]["fills"][0]["execution_states"] == ["NEW", "SUBMITTED", "PARTIAL", "CANCELLED"]
    now[0] += timedelta(minutes=1)
    cycles.append(app.process_frame(demo_frame(now[0], short_price="9.60")))
    reports = reports_from_cycles(cycles)
    assert reports["short"]["number_of_trades"] == 1
    assert reports["short"]["fee_cost"] > 0 and reports["short"]["slippage_cost"] > 0
    assert reports["short"]["initial_equity"] == 200000
    assert reports["long"]["initial_equity"] == 800000
    assert reports["short"]["expected_value_per_trade"] < 0
    assert reports["short"]["qualifies_as_elapsed_paper_evidence"] is False


def test_daily_report_finalize_is_idempotent_and_not_synthetic_elapsed_evidence(tmp_path):
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: START)
    app.process_frame(demo_frame(START))
    assert finalize_daily_reports(app.ledger, START) == 0
    assert finalize_daily_reports(app.ledger, START + timedelta(days=1)) == 1
    assert finalize_daily_reports(app.ledger, START + timedelta(days=1)) == 0
    report = [e for e in app.ledger.events() if e["kind"] == "DAILY_REPORT"][0]
    assert report["reports"]["short"]["synthetic"]
    assert not report["reports"]["short"]["live_ready"]


def test_model_training_cli_requires_preregistered_experiment():
    from aipro.cli import build_parser
    with pytest.raises(SystemExit):
        build_parser().parse_args(["model-train", "x.jsonl", "--symbol", "X", "--output-dir", "out"])
