"""CPU training, untouched final holdout, and explicit PAPER model export."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path
from statistics import fmean

from aipro.intelligence.classical_ml import CandidateStatus
from aipro.research.purged_training_runner import (
    LogisticTrainingConfig, _score_fold, fit_logistic_model, run_purged_logistic_training,
)
from aipro.research.purged_walk_forward import WalkForwardConfig
from aipro.us_stocks.model_artifact import (
    ARTIFACT_SCHEMA, ROBUST_ARTIFACT_SCHEMA, ModelArtifact, quality_blockers, robust_quality_blockers,
    validate_artifact, write_json_atomic,
)
from aipro.us_stocks.model_dataset import ModelDataset, build_model_dataset, fingerprint
from aipro.us_stocks.model_features import FEATURE_NAMES, FEATURE_SCHEMA
from aipro.us_stocks.portfolio_market import instant
from aipro.us_stocks.portfolio_policy import PortfolioPolicy
from aipro.research.experiment_ledger import ExperimentLedger, ExperimentSpec
from aipro.research.robust_statistics import BootstrapPolicy, mean_interval
from aipro.intelligence.calibration import fit_calibrator, reliability_report


@dataclass(frozen=True)
class ModelTrainingResult:
    artifact: ModelArtifact
    report: dict


def train_model(dataset: ModelDataset, *, policy: PortfolioPolicy | None = None,
                training: LogisticTrainingConfig | None = None,
                ledger: ExperimentLedger | None = None, experiment_id: str | None = None,
                calibration_method: str | None = "sigmoid") -> ModelTrainingResult:
    try:
        return _train_model(dataset, policy=policy, training=training, ledger=ledger,
                            experiment_id=experiment_id, calibration_method=calibration_method)
    except Exception as exc:
        if ledger is not None and experiment_id:
            ledger.record_failure(experiment_id, type(exc).__name__)
        raise


def _train_model(dataset: ModelDataset, *, policy, training, ledger, experiment_id,
                 calibration_method) -> ModelTrainingResult:
    policy = policy or PortfolioPolicy()
    if dataset.policy_fingerprint != policy.fingerprint:
        raise ValueError("dataset policy mismatch")
    if len(dataset.samples) < 600:
        raise ValueError("at least 600 disjoint labeled samples are required; no synthetic padding")
    if not dataset.synthetic and ledger is None:
        raise ValueError("real-data fitting requires the persistent experiment ledger")
    if ledger is not None and not experiment_id:
        raise ValueError("explicit experiment ID required")
    # Bid/ask spread is already reflected in executable-quote markout labels.
    minimum_cost_bps = float(2 * (policy.fee_rate + policy.fx_cost_rate + policy.slippage_rate) * 10000)
    training = training or LogisticTrainingConfig(epochs=150, estimated_round_trip_cost_bps=minimum_cost_bps)
    if training.estimated_round_trip_cost_bps < minimum_cost_bps:
        raise ValueError("training costs cannot be below the runtime cost assumption")
    holdout_size = max(100, len(dataset.samples) // 5)
    holdout_samples = dataset.samples[-holdout_size:]
    boundary = instant(holdout_samples[0].as_of_utc)
    development = tuple(s for s in dataset.samples[:-holdout_size] if instant(s.label_end_utc) < boundary)
    rows = tuple(sample.training_row() for sample in development)
    holdout = tuple(sample.training_row() for sample in holdout_samples)
    failure_rules = {"schema": "fixed-failure-v1", "min_holdout": 100, "min_trades": 30,
                     "max_brier": .25, "positive_ev_lower_bound": True, "double_cost_ev_positive": True,
                     "min_positive_walk_forward_fraction": .6, "calibration": calibration_method,
                     "bootstrap": asdict(BootstrapPolicy()), "cost_bps": training.estimated_round_trip_cost_bps,
                     "fixed_paper_artifact_lifetime_days": 90 if calibration_method else 7,
                     "portfolio_and_paper_validation_required": True}
    if ledger is not None:
        # Source fingerprints include the shared fitter, not only this wrapper.
        from hashlib import sha256
        from aipro.research import purged_training_runner
        code = sha256(Path(__file__).read_bytes() + Path(purged_training_runner.__file__).read_bytes()).hexdigest()
        ledger.register(ExperimentSpec(experiment_id, "us_stock", dataset.fingerprint, code,
                                       FEATURE_SCHEMA, failure_rules, trial_budget=1))
        ledger.reserve_trial(experiment_id, "logistic", asdict(training))
    calibration_rows = ()
    if calibration_method:
        count = 1000 if calibration_method == "isotonic" else 50
        calibration_rows = rows[-count:]
        rows = tuple(r for r in rows[:-count] if r.label_end < calibration_rows[0].index)
        if len(rows) < 400:
            raise ValueError("need at least 400 fitting rows plus separate calibration and final holdout")
    min_train = 80 if calibration_method else max(80, len(rows) // 3)
    test_size = (len(rows) - min_train) // 3
    walk_forward = WalkForwardConfig(min_train, test_size, test_size, embargo_size=1)
    report = run_purged_logistic_training(rows, candidate_name="us-short-logistic-v1",
        feature_names=FEATURE_NAMES, walk_forward=walk_forward, training=training)
    # Export precisely the model scored below. Do NOT refit on the final holdout.
    fitted = fit_logistic_model(rows, training)
    calibrator = None
    if calibration_method:
        calibrator = fit_calibrator(tuple(fitted.predict(r.features) for r in calibration_rows),
            tuple(r.target for r in calibration_rows), training_end=max(r.label_end for r in rows),
            calibration_indices=tuple(r.index for r in calibration_rows),
            calibration_label_ends=tuple(r.label_end for r in calibration_rows), test_start=holdout[0].index,
            method=calibration_method)
    if ledger is not None:
        ledger.open_holdout(experiment_id, "logistic", holdout_samples[0].as_of_utc, holdout_samples[-1].label_end_utc,
                            fingerprint({"model": asdict(fitted), "calibrator": asdict(calibrator) if calibrator else None}))
    if {row.target for row in holdout} != {0, 1}:
        raise ValueError("final holdout must contain both classes")
    probabilities = tuple(fitted.predict(row.features) for row in holdout)
    if calibrator:
        probabilities = tuple(calibrator.predict(p) for p in probabilities)
    scored = _score_fold(holdout, probabilities, training)
    prior = fmean(row.target for row in rows)
    selected = [row for row, probability in zip(holdout, probabilities) if probability >= training.decision_threshold]
    validation = {
        "cv_accepted": report.evaluation.status is CandidateStatus.ACCEPTED,
        "cv_samples": report.evaluation.total_samples, "cv_folds": len(report.folds),
        "holdout_samples": len(holdout), "selected_samples": len(selected),
        "balanced_accuracy": scored.balanced_accuracy, "brier_score": scored.brier_score,
        "prior_brier_score": fmean((prior - row.target) ** 2 for row in holdout),
        "net_ev_bps": scored.expected_value_bps,
        "stress_net_ev_bps": fmean(row.realized_return_bps - 2 * training.estimated_round_trip_cost_bps
                                   for row in selected) if selected else 0.0,
        "rule_net_ev_bps": fmean(row.realized_return_bps - training.estimated_round_trip_cost_bps for row in holdout),
    }
    blockers = quality_blockers(validation)
    selected_returns = [float(row.realized_return_bps - training.estimated_round_trip_cost_bps) / 10000 for row in selected]
    statistical = mean_interval(selected_returns) if len(selected_returns) >= 30 else None
    calibration_report = reliability_report(probabilities, tuple(r.target for r in holdout))
    robustness = {"net_ev_lower_bound": statistical["lower"] if statistical else None,
                  "positive_walk_forward_fraction": fmean(fold.expected_value_bps > 0 for fold in report.folds),
                  "ece": calibration_report["ece"], "calibrated": calibrator is not None}
    robust_blockers = robust_quality_blockers(robustness)
    blockers += robust_blockers
    gains = [row.realized_return_bps / 10000 for row in rows if row.realized_return_bps > 0]
    losses = [-row.realized_return_bps / 10000 for row in rows if row.realized_return_bps < 0]
    if not gains or not losses:
        raise ValueError("development data requires positive and negative markout evidence")
    training_end = max(instant(sample.label_end_utc) for sample in development)
    validation_end = max(instant(sample.label_end_utc) for sample in holdout_samples)
    result_report = {
        "schema": "aipro-us-model-report-v1", "symbol": dataset.symbol, "domain": "us_stock", "sleeve": "short",
        "paper_only": True, "live_ready": False, "qualifies_as_elapsed_paper_evidence": False,
        "synthetic": dataset.synthetic, "qualified": not blockers, "blockers": blockers,
        "dataset_fingerprint": dataset.fingerprint, "source_fingerprint": dataset.source_fingerprint,
        "feature_schema": FEATURE_SCHEMA, "feature_names": list(FEATURE_NAMES),
        "frame_count": dataset.frame_count, "sample_count": len(dataset.samples),
        "skipped_endpoints": dataset.skipped_endpoints, "horizon_seconds": dataset.horizon_seconds,
        "development_samples": len(rows), "training_end_utc": training_end.isoformat(),
        "holdout_start_utc": boundary.isoformat(), "validation_end_utc": validation_end.isoformat(),
        "training_configuration": asdict(training), "cross_validation": asdict(report),
        "validation": validation, "model_parameters_fingerprint": fingerprint(asdict(fitted)),
        "failure_policy": failure_rules, "experiment_id": experiment_id,
        "holdout_lock_enforced": ledger is not None, "markout_EV_interval": statistical,
        "statistical_blockers": robust_blockers, "promotion_eligible": False,
        "probability_calibration": calibration_report,
        "calibration_method": calibration_method, "calibration_samples": len(calibration_rows),
        "limitations": [
            "Fixed-horizon KRW bid/ask markouts are not realized strategy returns or portfolio drawdowns.",
            "Stops, queue position, session exits, capital constraints and corporate actions need full replay.",
            "Baseline comparison is conditional on sampled eligible signals and measures per-signal markout only.",
            "Markout block-bootstrap estimates are conditional on stationarity; they are not portfolio return evidence.",
            "The shared ledger blocks repeated holdout intervals for cooperating runners; deleting/copying the ledger defeats that local control.",
            "Input provenance markers and SHA-256 prove consistency, not supplier identity or data truth.",
            "Synthetic data validates software only. No real elapsed PAPER days or profitability are established.",
        ],
    }
    body = {
        "schema": ROBUST_ARTIFACT_SCHEMA, "domain": "us_stock", "sleeve": "short",
        "robustness": robustness, "calibrator": asdict(calibrator) if calibrator else None,
        "feature_schema": FEATURE_SCHEMA, "feature_names": list(FEATURE_NAMES), "symbol": dataset.symbol,
        "model": asdict(fitted), "policy_fingerprint": policy.fingerprint,
        "dataset_fingerprint": dataset.fingerprint, "report_fingerprint": fingerprint(result_report),
        "training_end_utc": training_end.isoformat(), "validation_end_utc": validation_end.isoformat(),
        "expires_at_utc": (validation_end + timedelta(days=7)).isoformat(),
        "synthetic": dataset.synthetic, "qualified": not blockers, "blockers": blockers, "validation": validation,
        "expected_gain_pct": fmean(gains), "expected_loss_pct": fmean(losses),
        "uncertainty": min(0.79, max(0.05, report.evaluation.metric_std + scored.brier_score ** 0.5)),
        "decision_threshold": training.decision_threshold, "horizon_seconds": dataset.horizon_seconds,
        "paper_only": True, "live_ready": False,
    }
    if calibrator:
        body["calibrator"] = asdict(calibrator)
        # A separately versioned, fixed PAPER validity horizon permits the
        # mandatory 30-day frozen-candidate shadow test. v1 remains seven days.
        body["expires_at_utc"] = (validation_end + timedelta(days=90)).isoformat()
    artifact = validate_artifact({"artifact": body, "fingerprint": fingerprint(body)})
    if ledger is not None:
        ledger.finish(experiment_id, {"report_fingerprint": fingerprint(result_report),
                                     "artifact_fingerprint": artifact.fingerprint,
                                     "statistical_blockers": robust_blockers})
    return ModelTrainingResult(artifact, result_report)


def train_from_archive(input_path: Path, *, symbol: str, output_dir: Path, horizon_seconds: int = 300,
                       experiment_id: str | None = None, ledger_path: Path = Path("data/research_experiments.sqlite3"),
                       calibration_method: str | None = "sigmoid") -> int:
    from aipro.us_stocks.portfolio_replay import load_jsonl
    # Protect the input against mistaken output-directory choices.
    if input_path.resolve() in {(output_dir / name).resolve() for name in ("model.json", "training_report.json")}:
        raise ValueError("training outputs must not overwrite the source archive")
    dataset = build_model_dataset(load_jsonl(input_path), symbol=symbol, horizon_seconds=horizon_seconds)
    if not experiment_id:
        raise ValueError("--experiment-id is required; failure criteria must be recorded before fitting")
    result = train_model(dataset, ledger=ExperimentLedger(ledger_path), experiment_id=experiment_id,
                         calibration_method=calibration_method)
    write_json_atomic(output_dir / "training_report.json", result.report)
    write_json_atomic(output_dir / "model.json", result.artifact.to_dict())
    print(f"PAPER research model: {result.artifact.model_id}")
    print(f"qualified={result.artifact.payload['qualified']}; synthetic={dataset.synthetic}; live_ready=False")
    print(f"blockers={result.artifact.payload['blockers']}")
    return 0 if result.artifact.payload["qualified"] else 1
