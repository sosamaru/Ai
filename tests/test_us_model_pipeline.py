"""Synthetic software tests only; none is actual market or elapsed PAPER evidence."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
import json

import pytest

from aipro.config import Settings
from aipro.us_stocks.model_artifact import ArtifactForecastProvider, load_artifact, validate_artifact, write_json_atomic
from aipro.us_stocks.model_dataset import ModelDataset, ModelSample, build_model_dataset, fingerprint
from aipro.us_stocks.model_features import model_features
from aipro.us_stocks.model_training import train_model
from aipro.us_stocks.portfolio_application import TradingApplication
from aipro.us_stocks.portfolio_policy import PortfolioPolicy
from aipro.us_stocks.portfolio_replay import demo_frame

START = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)


def synthetic_dataset():
    frame = demo_frame(START)
    base, fp = model_features(frame.quotes[0], START)
    samples = []
    for index in range(600):
        at = START - timedelta(minutes=6 * (601 - index))
        positive = index % 2 == 1
        values = (base[0] if positive else base[0] - 0.2, *base[1:])
        samples.append(ModelSample(at.isoformat(), (at + timedelta(minutes=5)).isoformat(),
                                   values, 400.0 if positive else -150.0, fp))
    return ModelDataset("SIMS", 300, True, PortfolioPolicy().fingerprint, "a" * 64, tuple(samples), 1200)


@pytest.fixture(scope="module")
def trained():
    return train_model(synthetic_dataset())


def test_real_numeric_fit_is_deterministic_and_beats_prior_on_synthetic_holdout(trained):
    again = train_model(synthetic_dataset())
    assert trained.artifact.fingerprint == again.artifact.fingerprint
    assert trained.artifact.payload["qualified"]
    assert trained.report["validation"]["balanced_accuracy"] == 1
    assert trained.report["validation"]["stress_net_ev_bps"] > 0
    assert trained.report["synthetic"] and trained.report["live_ready"] is False
    assert trained.report["qualifies_as_elapsed_paper_evidence"] is False


def test_final_holdout_cannot_change_fitted_parameters(trained):
    dataset = synthetic_dataset()
    changed = replace(dataset, samples=dataset.samples[:480] + tuple(
        replace(sample, gross_return_bps=-sample.gross_return_bps) for sample in dataset.samples[480:]))
    other = train_model(changed)
    assert other.artifact.model == trained.artifact.model
    assert not other.artifact.payload["qualified"]
    assert other.artifact.payload["blockers"]


def test_archive_labels_are_disjoint_and_use_future_bid_with_fx():
    frames = tuple(demo_frame(START + timedelta(minutes=i), short_price="10.80" if i == 5 else "10.46") for i in range(12))
    dataset = build_model_dataset(frames, symbol="SIMS")
    assert len(dataset.samples) == 2
    expected = float((frames[5].quotes[0].bid / frames[0].quotes[0].ask - 1) * 10000)
    assert dataset.samples[0].gross_return_bps == pytest.approx(expected)
    assert dataset.samples[0].label_end_utc < dataset.samples[1].as_of_utc
    assert dataset.synthetic


def test_missing_exact_endpoint_is_skipped_without_interpolation():
    frames = tuple(demo_frame(START + timedelta(minutes=i)) for i in range(14) if i != 5)
    dataset = build_model_dataset(frames, symbol="SIMS")
    assert dataset.skipped_endpoints >= 1
    assert dataset.samples[0].as_of_utc != START.isoformat()


def test_training_input_rejects_reordered_and_mixed_provenance():
    first, later = demo_frame(START), demo_frame(START + timedelta(minutes=1))
    with pytest.raises(ValueError, match="chronological"):
        build_model_dataset([later, first], symbol="SIMS")
    with pytest.raises(ValueError, match="cannot be mixed"):
        build_model_dataset([first, replace(later, synthetic=False)], symbol="SIMS")


def test_small_dataset_cannot_be_padded_into_acceptance():
    dataset = synthetic_dataset()
    with pytest.raises(ValueError, match="600"):
        train_model(replace(dataset, samples=dataset.samples[:100]))


def test_artifact_roundtrip_and_pinning(tmp_path, trained):
    path = tmp_path / "model.json"
    write_json_atomic(path, trained.artifact.to_dict())
    restored = load_artifact(path, expected_fingerprint=trained.artifact.fingerprint)
    assert restored.model == trained.artifact.model
    with pytest.raises(ValueError, match="pinned"):
        load_artifact(path, expected_fingerprint="0" * 64)
    raw = json.loads(path.read_text())
    raw["artifact"]["model"]["weights"][0] += 1
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="fingerprint"):
        load_artifact(path)


@pytest.mark.parametrize("mutation", [
    lambda b: b.update(domain="crypto"),
    lambda b: b.update(feature_names=list(reversed(b["feature_names"]))),
    lambda b: b.update(live_ready=True),
    lambda b: b["validation"].update(selected_samples=True),
    lambda b: b["validation"].update(net_ev_bps=-1),
    lambda b: b["model"].update(scales=[0] * 8),
])
def test_rehashed_but_invalid_artifact_is_rejected(trained, mutation):
    body = deepcopy(trained.artifact.payload)
    mutation(body)
    with pytest.raises(ValueError):
        validate_artifact({"artifact": body, "fingerprint": fingerprint(body)})


def test_json_loader_rejects_duplicate_keys_and_large_input(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"artifact":{},"artifact":{}}')
    with pytest.raises(ValueError, match="duplicate"):
        load_artifact(path)
    path.write_bytes(b" " * 1_000_001)
    with pytest.raises(ValueError, match="1 MB"):
        load_artifact(path)


def test_synthetic_artifact_cannot_be_loaded_as_operating_model(trained):
    with pytest.raises(ValueError, match="synthetic"):
        ArtifactForecastProvider(trained.artifact)


def test_forecast_reuses_fitted_scaler_and_enters_only_through_existing_gates(tmp_path, trained):
    provider = ArtifactForecastProvider(trained.artifact, allow_synthetic=True)
    frame = demo_frame(START)
    values, fp = model_features(frame.quotes[0], START)
    forecast = provider.forecast_frame(frame.quotes[0], frame, PortfolioPolicy(), fp)
    assert forecast is not None
    assert forecast.win_probability == trained.artifact.model.predict(values)
    app = TradingApplication(Settings(), db_path=tmp_path / "us.db", forecaster=provider, clock=lambda: START)
    result = app.process_frame(frame)
    assert any(d.get("model_id") == provider.model_id for d in result["decisions"])
    assert any(f["side"] == "BUY" and f["sleeve"] == "short" for f in result["fills"])
    assert app.status()["short_model_id"] == provider.model_id
    assert result["status"]["remaining_external_funding_krw"] == "0"


@pytest.mark.parametrize("case,reason", [
    ("future", "future_evidence"), ("expired", "expired"), ("symbol", "symbol_mismatch"),
    ("provenance", "provenance_mismatch"), ("policy", "policy_mismatch"), ("lineage", "lineage_mismatch"),
])
def test_model_abstains_on_invalid_scope_or_time(trained, case, reason):
    provider = ArtifactForecastProvider(trained.artifact, allow_synthetic=True)
    frame, policy = demo_frame(START), PortfolioPolicy()
    if case == "future":
        frame = demo_frame(START - timedelta(minutes=20))
    if case == "expired":
        frame = demo_frame(START + timedelta(days=8))
    if case == "provenance":
        frame = replace(frame, synthetic=False)
    if case == "policy":
        policy = replace(policy, fee_rate=policy.fee_rate * 2)
    quote = frame.quotes[0]
    if case == "symbol":
        quote = replace(quote, symbol="OTHER")
    _, fp = model_features(quote, frame.as_of_utc)
    assert provider.forecast_frame(quote, frame, policy, "0" * 64 if case == "lineage" else fp) is None
    assert reason in provider.last_reason


def test_drifted_features_abstain(trained):
    provider = ArtifactForecastProvider(trained.artifact, allow_synthetic=True)
    frame = demo_frame(START)
    quote = replace(frame.quotes[0], intraday_bars=tuple(replace(b, volume=b.volume * 100) for b in frame.quotes[0].intraday_bars))
    _, fp = model_features(quote, START)
    assert provider.forecast_frame(quote, frame, PortfolioPolicy(), fp) is None
    assert provider.last_reason == "model_feature_out_of_distribution"


def test_canonical_application_loads_only_explicitly_pinned_real_marker_fixture(tmp_path, monkeypatch, trained):
    # This deliberately edited metadata is a TEST fixture, never market evidence.
    body = deepcopy(trained.artifact.payload)
    body["synthetic"] = False
    artifact = validate_artifact({"artifact": body, "fingerprint": fingerprint(body)})
    path = tmp_path / "model.json"
    write_json_atomic(path, artifact.to_dict())
    monkeypatch.setenv("AIPRO_RUNTIME", "US_DUAL")
    monkeypatch.setenv("AIPRO_US_DUAL_DB_PATH", str(tmp_path / "us.db"))
    monkeypatch.setenv("AIPRO_LOG_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("AIPRO_US_MODEL_PATH", str(path))
    monkeypatch.setenv("AIPRO_US_MODEL_SHA256", artifact.fingerprint)
    from main import build_application
    app = build_application()
    assert app.asset_class == "us_stock" and app.forecaster.model_id == artifact.model_id
    monkeypatch.setenv("AIPRO_US_MODEL_SHA256", "")
    with pytest.raises(ValueError, match="both"):
        build_application()
