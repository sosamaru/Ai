"""Invented quotes exercise prospective capture; never actual PAPER evidence."""
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json
import pytest

from aipro.config import Settings
from aipro.us_stocks.market_capture import FrameArchive
from aipro.us_stocks.portfolio_application import TradingApplication
from aipro.us_stocks.portfolio_replay import demo_frame, load_jsonl

START = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)


def test_capture_is_restart_safe_and_exports_identical_feature_inputs(tmp_path):
    frame = replace(demo_frame(START), synthetic=False)  # metadata fixture only
    store = FrameArchive(tmp_path / "capture.db")
    assert store.append(frame, captured_at=START)
    assert not FrameArchive(store.path).append(frame, captured_at=START + timedelta(seconds=1))
    path = tmp_path / "frames.jsonl"
    assert store.export(path) == 1
    assert tuple(load_jsonl(path))[0].fingerprint == frame.fingerprint
    with pytest.raises(FileExistsError):
        store.export(path)
    with pytest.raises(ValueError, match="overwrite"):
        store.export(store.path)


def test_capture_rejects_replay_synthetic_and_reversed_observations(tmp_path):
    store = FrameArchive(tmp_path / "capture.db")
    with pytest.raises(ValueError, match="prospective"):
        store.append(demo_frame(START), captured_at=START)
    frame = replace(demo_frame(START), synthetic=False)
    with pytest.raises(ValueError, match="prospective"):
        store.append(frame, captured_at=START + timedelta(days=1))
    store.append(frame, captured_at=START)
    with pytest.raises(ValueError, match="reverse"):
        store.append(replace(frame, source="different-same-time"), captured_at=START)


def test_canonical_file_paper_runtime_records_current_frames_before_orders(tmp_path, monkeypatch):
    path = tmp_path / "frame.json"
    frame = replace(demo_frame(START), synthetic=False)
    path.write_text(json.dumps(frame.to_dict()))
    monkeypatch.setenv("AIPRO_US_FRAME_PATH", str(path))
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: START)
    assert app.run_once()["processed"]
    archive = FrameArchive(tmp_path / "us.db.frames.sqlite3")
    assert archive.export(tmp_path / "export.jsonl") == 1


def test_model_horizon_exit_and_explanations_are_in_actual_paper_cycle(tmp_path):
    from aipro.intelligence.paper_strategy_validation import ForecastEvidence
    class Forecast:
        def forecast(self, quote, feature_fingerprint):
            return ForecastEvidence(.9, .04, .02, .1, "TEST_MODEL", feature_fingerprint,
                                    probability_calibrated=True, horizon_seconds=300)
    now = [START]
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: now[0], forecaster=Forecast())
    result = app.process_frame(demo_frame(START))
    assert any(d.get("net_ev_fraction") is not None and d.get("action") == "LONG" for d in result["decisions"])
    now[0] += timedelta(minutes=5)
    result = app.process_frame(demo_frame(now[0]))
    assert any(f["reason"] == "forecast_time_stop" and f["action"] == "EXIT" for f in result["fills"])
