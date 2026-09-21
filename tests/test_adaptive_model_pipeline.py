"""Synthetic numeric training/inference and local shadow integration only."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import timedelta

import pytest

from aipro.config import Settings
from aipro.core.evidence import fingerprint
from aipro.core.performance import EquityObservation
from aipro.intelligence.promotion import PerformanceEvidence
from aipro.research.experiment_ledger import ExperimentLedger
from aipro.research.purged_training_runner import LogisticTrainingConfig
from aipro.us_stocks.ensemble_forecast import EnsembleForecastProvider, load_ensemble
from aipro.us_stocks.model_artifact import ArtifactForecastProvider, load_artifact, validate_artifact, write_json_atomic
from aipro.us_stocks.model_features import model_features
from aipro.us_stocks.model_training import train_model
from aipro.us_stocks.portfolio_application import TradingApplication
from aipro.us_stocks.portfolio_policy import PortfolioPolicy
from aipro.us_stocks.portfolio_replay import demo_frame
from aipro.us_stocks.shadow_cohort import ShadowCohort
from test_us_model_pipeline import START, synthetic_dataset


@pytest.fixture(scope="module")
def calibrated():
    return train_model(synthetic_dataset(), calibration_method="sigmoid")


def test_calibrated_model_persists_and_uses_separate_partition(tmp_path, calibrated):
    result = calibrated
    assert result.artifact.payload["schema"].endswith("v3")
    assert result.report["calibration_samples"] == 50
    assert result.report["probability_calibration"]["observations"] == 120
    assert result.report["promotion_eligible"] is False
    path = tmp_path / "model.json"
    write_json_atomic(path, result.artifact.to_dict())
    artifact = load_artifact(path, expected_fingerprint=result.artifact.fingerprint)
    provider = ArtifactForecastProvider(artifact, allow_synthetic=True)
    frame = demo_frame(START)
    values, fp = model_features(frame.quotes[0], START)
    forecast = provider.forecast_frame(frame.quotes[0], frame, PortfolioPolicy(), fp)
    from aipro.intelligence.calibration import Calibrator
    assert forecast.win_probability == pytest.approx(Calibrator(**artifact.payload["calibrator"]).predict(artifact.model.predict(values)))


def test_persistent_training_ledger_blocks_final_reuse_even_new_experiment_id(tmp_path):
    ledger = ExperimentLedger(tmp_path / "research.db")
    first = train_model(synthetic_dataset(), ledger=ledger, experiment_id="first")
    assert first.report["holdout_lock_enforced"]
    with pytest.raises(ValueError, match="overlaps"):
        train_model(synthetic_dataset(), ledger=ledger, experiment_id="renamed")
    with pytest.raises(ValueError, match="requires the persistent"):
        train_model(replace(synthetic_dataset(), synthetic=False))


def test_calibration_never_learns_from_final_holdout(calibrated):
    data = synthetic_dataset()
    changed = replace(data, samples=data.samples[:480] + tuple(replace(s, gross_return_bps=-s.gross_return_bps) for s in data.samples[480:]))
    result = train_model(changed, calibration_method="sigmoid")
    assert result.artifact.model == calibrated.artifact.model
    assert result.artifact.payload["calibrator"] == calibrated.artifact.payload["calibrator"]
    assert not result.artifact.payload["qualified"]


def test_ensemble_is_live_wired_restart_safe_and_cannot_collapse_to_single_model(tmp_path, calibrated):
    other = train_model(synthetic_dataset(), calibration_method="sigmoid", training=LogisticTrainingConfig(epochs=100, estimated_round_trip_cost_bps=50))
    providers = [ArtifactForecastProvider(r.artifact, allow_synthetic=True) for r in (calibrated, other)]
    source = EnsembleForecastProvider(providers, state_path=tmp_path / "ensemble.db", allow_synthetic=True)
    frame = demo_frame(START)
    _, fp = model_features(frame.quotes[0], START)
    forecast = source.forecast_frame(frame.quotes[0], frame, PortfolioPolicy(), fp)
    assert forecast and forecast.model_id == source.model_id
    assert max(source.last_report["weights"].values()) <= .6
    restored = EnsembleForecastProvider(providers, state_path=tmp_path / "ensemble.db", allow_synthetic=True)
    assert restored.forecast_frame(frame.quotes[0], frame, PortfolioPolicy(), fp) is None
    assert "duplicate" in restored.last_reason
    with pytest.raises(ValueError, match="distinct"):
        EnsembleForecastProvider(providers[:1], state_path=tmp_path / "bad.db", allow_synthetic=True)


def test_ensemble_manifest_rejects_pin_and_path_escape(tmp_path):
    body = {"schema": "aipro-paper-ensemble-v1", "models": [
        {"path": "../outside.json", "fingerprint": "a"*64}, {"path": "x.json", "fingerprint": "b"*64}]}
    path = tmp_path / "ensemble.json"
    write_json_atomic(path, body)
    with pytest.raises(ValueError, match="pin"):
        load_ensemble(path, expected_fingerprint="0"*64, state_path=tmp_path / "state.db")
    with pytest.raises(ValueError, match="inside"):
        load_ensemble(path, expected_fingerprint=fingerprint(body), state_path=tmp_path / "state.db")


def test_shadow_cohort_captures_actual_call_time_and_keeps_books_isolated(tmp_path, calibrated):
    # Metadata intentionally changed ONLY to exercise software; no real-data claim.
    providers, oos = [], {}
    for offset in (0., .01):
        body = deepcopy(calibrated.artifact.payload)
        body["synthetic"] = False
        body["model"]["bias"] += offset
        artifact = validate_artifact({"artifact": body, "fingerprint": fingerprint(body)})
        providers.append(ArtifactForecastProvider(artifact))
        points = tuple(EquityObservation((START - timedelta(minutes=5 - i)).isoformat(), 200000.) for i in range(2))
        oos[artifact.fingerprint] = PerformanceEvidence("us_stock", artifact.fingerprint, "d"*64, "oos", points, (),
            0., 0., 0., .1, .1, .01, .8, False, points[0].at, points[-1].at)
    clock = [START]
    cohort = ShadowCohort(providers, oos, directory=tmp_path / "shadow", settings=Settings(), policy=PortfolioPolicy(), clock=lambda: clock[0])
    with pytest.raises(ValueError, match="non-synthetic"):
        cohort.observe(demo_frame(START))
    frame = replace(demo_frame(START), synthetic=False)
    cohort.observe(frame)
    assert len({app.ledger.path for app in cohort.apps.values()}) == 2
    for app in cohort.apps.values():
        assert app.ledger.read()["external_contributed_krw"] == "1000000"
    assert cohort.store.current("us_stock") == providers[0].artifact.fingerprint
    # Replayed old prices at a newer wall clock are refused as prospective evidence.
    clock[0] += timedelta(days=1)
    with pytest.raises(ValueError, match="current"):
        cohort.observe(frame)
