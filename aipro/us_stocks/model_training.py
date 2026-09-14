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
    ARTIFACT_SCHEMA, ModelArtifact, quality_blockers, validate_artifact, write_json_atomic,
)
from aipro.us_stocks.model_dataset import ModelDataset, build_model_dataset, fingerprint
from aipro.us_stocks.model_features import FEATURE_NAMES, FEATURE_SCHEMA
from aipro.us_stocks.portfolio_market import instant
from aipro.us_stocks.portfolio_policy import PortfolioPolicy


@dataclass(frozen=True)
class ModelTrainingResult:
    artifact: ModelArtifact
    report: dict


def train_model(dataset: ModelDataset, *, policy: PortfolioPolicy | None = None,
                training: LogisticTrainingConfig | None = None) -> ModelTrainingResult:
    policy = policy or PortfolioPolicy()
    if dataset.policy_fingerprint != policy.fingerprint:
        raise ValueError("dataset policy mismatch")
    if len(dataset.samples) < 600:
        raise ValueError("at least 600 disjoint labeled samples are required; no synthetic padding")
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
    if {row.target for row in holdout} != {0, 1}:
        raise ValueError("final holdout must contain both classes")
    min_train = max(80, len(rows) // 3)
    test_size = (len(rows) - min_train) // 3
    walk_forward = WalkForwardConfig(min_train, test_size, test_size, embargo_size=1)
    report = run_purged_logistic_training(rows, candidate_name="us-short-logistic-v1",
        feature_names=FEATURE_NAMES, walk_forward=walk_forward, training=training)
    # Export precisely the model scored below. Do NOT refit on the final holdout.
    fitted = fit_logistic_model(rows, training)
    probabilities = tuple(fitted.predict(row.features) for row in holdout)
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
        "limitations": [
            "Fixed-horizon KRW bid/ask markouts are not realized strategy returns or portfolio drawdowns.",
            "Stops, queue position, session exits, capital constraints and corporate actions need full replay.",
            "Baseline comparison is conditional on sampled eligible signals and measures per-signal markout only.",
            "Non-overlapping labels can remain serially dependent; no statistical significance is claimed.",
            "Repeated research against this holdout invalidates its independence; use a new later holdout.",
            "Input provenance markers and SHA-256 prove consistency, not supplier identity or data truth.",
            "Synthetic data validates software only. No real elapsed PAPER days or profitability are established.",
        ],
    }
    body = {
        "schema": ARTIFACT_SCHEMA, "domain": "us_stock", "sleeve": "short",
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
    artifact = validate_artifact({"artifact": body, "fingerprint": fingerprint(body)})
    return ModelTrainingResult(artifact, result_report)


def train_from_archive(input_path: Path, *, symbol: str, output_dir: Path, horizon_seconds: int = 300) -> int:
    from aipro.us_stocks.portfolio_replay import load_jsonl
    # Protect the input against mistaken output-directory choices.
    if input_path.resolve() in {(output_dir / name).resolve() for name in ("model.json", "training_report.json")}:
        raise ValueError("training outputs must not overwrite the source archive")
    dataset = build_model_dataset(load_jsonl(input_path), symbol=symbol, horizon_seconds=horizon_seconds)
    result = train_model(dataset)
    write_json_atomic(output_dir / "training_report.json", result.report)
    write_json_atomic(output_dir / "model.json", result.artifact.to_dict())
    print(f"PAPER research model: {result.artifact.model_id}")
    print(f"qualified={result.artifact.payload['qualified']}; synthetic={dataset.synthetic}; live_ready=False")
    print(f"blockers={result.artifact.payload['blockers']}")
    return 0 if result.artifact.payload["qualified"] else 1
