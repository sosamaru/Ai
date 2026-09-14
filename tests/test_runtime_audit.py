from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from urllib.error import URLError

import pytest

from aipro.config import Settings
from aipro.intelligence.classical_ml import ModelDomain
from aipro.intelligence.paper_strategy_validation import ForecastEvidence
from aipro.research.purged_training_runner import LogisticTrainingConfig, TrainingRow, run_purged_logistic_training
from aipro.research.purged_walk_forward import Observation, PurgedWalkForwardSplitter, WalkForwardConfig, assert_no_leakage
from aipro.us_stocks.portfolio_application import TradingApplication
from aipro.us_stocks.portfolio_market import MarketFrame
from aipro.us_stocks.portfolio_replay import demo_frame
from telegram import TelegramBotClient


def test_training_labels_must_be_known_at_test_prediction_even_if_test_labels_start_later():
    observations = [Observation(i, i + 3, i + 4, "us_stock") for i in range(20)]
    folds = PurgedWalkForwardSplitter(WalkForwardConfig(8, 4, 4)).split(observations)
    for fold in folds:
        assert all(observations[i].label_end < min(fold.test_indices) for i in fold.train_indices)
        assert_no_leakage(fold, observations)
    assert 4 not in folds[0].train_indices  # Its answer becomes available at test time.


def test_prior_embargo_is_actually_excluded_from_later_training():
    observations = [Observation(i, i, i, "crypto") for i in range(24)]
    folds = PurgedWalkForwardSplitter(WalkForwardConfig(8, 4, 4, embargo_size=2)).split(observations)
    assert folds[0].embargoed_indices == (12, 13)
    assert not {12, 13}.intersection(folds[2].train_indices)


def test_zero_remaining_training_evidence_and_duplicate_test_evidence_are_rejected():
    with pytest.raises(ValueError, match="insufficient"):
        PurgedWalkForwardSplitter(WalkForwardConfig(4, 2, 2)).split(
            [Observation(i, i, i + 100, "crypto") for i in range(8)])
    with pytest.raises(ValueError, match="counted twice"):
        WalkForwardConfig(4, 3, 1).validate()


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1])
def test_invalid_training_cost_is_not_accepted(bad):
    with pytest.raises(ValueError):
        LogisticTrainingConfig(estimated_round_trip_cost_bps=bad)


@pytest.mark.parametrize("field,value", [("expectancy_per_trade_pct", float("nan")),
    ("maximum_drawdown_pct", float("inf")), ("completed_orders", -1),
    ("completed_sessions", True), ("started_at_utc", "2026-01-01T00:00:00")])
def test_invalid_operational_evidence_cannot_qualify(field, value):
    from aipro.us_stocks.paper_training import PaperTrainingEvidence
    data = dict(started_at_utc="2026-01-01T00:00:00+00:00", evaluated_at_utc="2026-02-01T00:00:00+00:00",
        completed_sessions=22, completed_orders=80, net_return_pct=2.0, maximum_drawdown_pct=1.0,
        worst_daily_return_pct=-0.5, expectancy_per_trade_pct=0.1, stale_data_events=0,
        duplicate_order_events=0, unreconciled_order_events=0)
    data[field] = value
    with pytest.raises(ValueError):
        PaperTrainingEvidence(**data)


def test_nonfinite_model_acceptance_threshold_cannot_disable_a_gate():
    from aipro.intelligence.classical_ml import EvaluationPolicy
    with pytest.raises(ValueError, match="finite"):
        EvaluationPolicy(min_expected_value_bps=float("nan"))


def test_single_class_training_fold_is_rejected_even_with_two_class_dataset():
    rows = [TrainingRow(i, i, i, ModelDomain.US_STOCK, (float(i),), int(i >= 8), 10) for i in range(20)]
    with pytest.raises(ValueError, match="both target classes"):
        run_purged_logistic_training(rows, candidate_name="audit", feature_names=("x",),
                                    walk_forward=WalkForwardConfig(6, 4, 4))


def test_telegram_network_errors_do_not_expose_token_url(monkeypatch):
    token = "TEST_ONLY_TOKEN_NEVER_REAL"
    client = TelegramBotClient(token, 1)
    def fail(*args, **kwargs):
        raise URLError(f"https://api.telegram.org/bot{token}/getUpdates")
    monkeypatch.setattr("telegram.request.urlopen", fail)
    with pytest.raises(RuntimeError) as error:
        client.get_updates()
    assert token not in str(error.value)
    assert "api.telegram" not in str(error.value)


def test_telegram_duplicate_bool_negative_and_stale_update_ids_do_not_repeat_commands(monkeypatch):
    client = TelegramBotClient("test-token", 1)
    client.offset = 4
    monkeypatch.setattr(client, "_call", lambda *args: {"result": [
        {"update_id": i} for i in (True, -1, 2, 6, 4, 6, 5)]})
    assert [u["update_id"] for u in client.get_updates()] == [4, 5, 6]
    assert client.offset == 7


def test_malformed_nested_telegram_message_does_not_kill_polling(monkeypatch):
    from types import SimpleNamespace
    import telegram
    client = TelegramBotClient("test-token", 1)
    calls = []
    def updates():
        if calls:
            raise KeyboardInterrupt
        calls.append(True)
        return [{"message": "invalid"}, {"message": {"chat": [1]}}]
    monkeypatch.setattr(client, "get_updates", updates)
    monkeypatch.setattr(telegram, "TelegramBotClient", lambda *args: client)
    app = SimpleNamespace(asset_class="us_stock", settings=Settings(telegram_bot_token="test-token"))
    assert telegram._run_polling(app) == 0


@pytest.mark.parametrize("raw", [None, [], {"quotes": None}, {"quotes": [42]}, {"quotes": [{}]}])
def test_malformed_market_frame_has_actionable_value_error(raw):
    with pytest.raises(ValueError):
        MarketFrame.from_dict(raw)


def test_missing_market_input_returns_failure_from_canonical_console(monkeypatch, tmp_path):
    import telegram
    monkeypatch.delenv("AIPRO_US_FRAME_PATH", raising=False)
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db")
    monkeypatch.setattr(telegram, "build_application", lambda: app)
    assert telegram.launch() == 1
    assert app.ledger.read()["sleeves"]["short"]["cash"] == "200000"


@pytest.mark.parametrize("failure", ["raises", "nan", "wrong_object", "zero_loss", "invalid_id"])
def test_model_failure_cannot_prevent_existing_long_risk_exit(tmp_path, failure):
    start = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    now = [start]
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", clock=lambda: now[0])
    first = demo_frame(start)
    app.process_frame(replace(first, quotes=(first.quotes[1],)))
    assert app.ledger.read()["sleeves"]["long"]["positions"]
    class BrokenModel:
        def forecast(self, quote, feature_fingerprint):
            if failure == "nan":
                return ForecastEvidence(float("nan"), 0.04, 0.02, 0.1, "test", feature_fingerprint)
            if failure == "wrong_object":
                return {"unexpected": True}
            if failure == "zero_loss":
                return ForecastEvidence(0.9, 0.04, 0, 0.1, "test", feature_fingerprint)
            if failure == "invalid_id":
                return ForecastEvidence(0.9, 0.04, 0.02, 0.1, "", feature_fingerprint)
            raise RuntimeError("TEST_PRIVATE_PROVIDER_TEXT")
    app.forecaster = BrokenModel()
    now[0] += timedelta(minutes=1)
    frame = demo_frame(now[0])
    frame = replace(frame, quotes=(frame.quotes[0], replace(frame.quotes[1], intelligence=
        replace(frame.quotes[1].intelligence, material_risk=True))))
    result = app.process_frame(frame)
    assert any(f["side"] == "SELL" and f["sleeve"] == "long" for f in result["fills"])
    assert not app.ledger.read()["sleeves"]["short"]["positions"]
    assert any(d["reason"].startswith("forecast_error") for d in result["decisions"])
    assert "TEST_PRIVATE_PROVIDER_TEXT" not in str(result)
