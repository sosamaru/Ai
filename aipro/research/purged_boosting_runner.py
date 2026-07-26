"""Bounded optional gradient-boosting training on purged PAPER folds.

Third-party backends remain lazy. This module creates an estimator only after
row, domain, fold, and resource validation. It never persists models, contacts
brokers, submits orders, or grants execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Any, Mapping, Sequence

from aipro.intelligence.classical_ml import (
    CandidateFamily,
    CandidateSpec,
    EvaluationPolicy,
    FoldMetrics,
    ModelDomain,
    evaluate_candidate,
)
from aipro.intelligence.optional_boosting import build_backend
from aipro.research.purged_training_runner import (
    PurgedFoldTrainingEvidence,
    PurgedTrainingReport,
    TrainingRow,
    _score_fold,
    _validate_rows,
)
from aipro.research.purged_walk_forward import (
    Observation,
    PurgedWalkForwardSplitter,
    WalkForwardConfig,
    assert_no_leakage,
)

_ALLOWED_BACKENDS = frozenset({"xgboost", "lightgbm", "catboost"})


@dataclass(frozen=True)
class BoostingTrainingConfig:
    backend: str
    parameters: Mapping[str, Any] | None = None
    decision_threshold: float = 0.5
    estimated_round_trip_cost_bps: float = 5.0

    def __post_init__(self) -> None:
        normalized = self.backend.strip().lower()
        if normalized not in _ALLOWED_BACKENDS:
            raise ValueError(f"unsupported boosting backend: {self.backend!r}")
        if not 0.0 < self.decision_threshold < 1.0:
            raise ValueError("decision_threshold must be in (0, 1)")
        if not math.isfinite(self.estimated_round_trip_cost_bps) or self.estimated_round_trip_cost_bps < 0:
            raise ValueError("estimated_round_trip_cost_bps must be finite and non-negative")


@dataclass(frozen=True)
class _ScoringConfig:
    decision_threshold: float
    estimated_round_trip_cost_bps: float


def run_purged_boosting_training(
    rows: Sequence[TrainingRow],
    *,
    candidate_name: str,
    feature_names: Sequence[str],
    walk_forward: WalkForwardConfig,
    training: BoostingTrainingConfig,
    evaluation_policy: EvaluationPolicy | None = None,
) -> PurgedTrainingReport:
    """Fit and evaluate one optional boosting candidate across purged folds."""

    ordered = _validate_rows(rows, feature_names)
    domain = ordered[0].domain
    backend = training.backend.strip().lower()
    parameters = dict(training.parameters or {})
    splitter = PurgedWalkForwardSplitter(walk_forward)
    observations = tuple(
        Observation(row.index, row.label_start, row.label_end, row.domain.value)
        for row in ordered
    )
    folds = splitter.split(observations)
    by_index = {row.index: row for row in ordered}
    evidence: list[PurgedFoldTrainingEvidence] = []
    metrics: list[FoldMetrics] = []
    scoring = _ScoringConfig(
        decision_threshold=training.decision_threshold,
        estimated_round_trip_cost_bps=training.estimated_round_trip_cost_bps,
    )

    for fold in folds:
        assert_no_leakage(fold, observations)
        train_rows = tuple(by_index[index] for index in fold.train_indices)
        test_rows = tuple(by_index[index] for index in fold.test_indices)
        estimator = build_backend(backend, parameters)
        x_train = tuple(row.features for row in train_rows)
        y_train = tuple(row.target for row in train_rows)
        x_test = tuple(row.features for row in test_rows)
        estimator.fit(x_train, y_train)
        probabilities = _positive_probabilities(estimator, x_test)
        fold_metrics = _score_fold(test_rows, probabilities, scoring)
        metrics.append(fold_metrics)
        model_fingerprint = _fold_model_fingerprint(
            backend=backend,
            parameters=parameters,
            fold_fingerprint=fold.fingerprint,
            probabilities=probabilities,
        )
        evidence.append(
            PurgedFoldTrainingEvidence(
                fold_fingerprint=fold.fingerprint,
                train_count=len(train_rows),
                test_count=len(test_rows),
                purged_count=len(fold.purged_indices),
                embargoed_count=len(fold.embargoed_indices),
                balanced_accuracy=fold_metrics.balanced_accuracy,
                brier_score=fold_metrics.brier_score,
                expected_value_bps=fold_metrics.expected_value_bps,
                turnover=fold_metrics.turnover,
                model_fingerprint=model_fingerprint,
            )
        )

    spec = CandidateSpec(
        name=candidate_name,
        family=CandidateFamily.GRADIENT_BOOSTING,
        domain=domain,
        feature_names=tuple(feature_names),
        target_name="forward_return_positive",
        random_seed=_seed_for(backend, parameters),
        parameters={
            "backend": backend,
            **parameters,
            "decision_threshold": training.decision_threshold,
            "estimated_round_trip_cost_bps": training.estimated_round_trip_cost_bps,
            "validation": "purged_walk_forward",
        },
    )
    evaluation = evaluate_candidate(spec, metrics, evaluation_policy)
    payload = {
        "domain": domain.value,
        "candidate_name": candidate_name,
        "backend": backend,
        "folds": [item.__dict__ for item in evidence],
        "evaluation_fingerprint": evaluation.fingerprint,
        "paper_only": True,
        "grants_execution_authority": False,
    }
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return PurgedTrainingReport(
        domain=domain,
        candidate_name=candidate_name,
        folds=tuple(evidence),
        evaluation=evaluation,
        fingerprint=fingerprint,
    )


def _positive_probabilities(estimator: Any, x_test: Sequence[Sequence[float]]) -> tuple[float, ...]:
    raw = estimator.predict_proba(x_test)
    probabilities: list[float] = []
    for row in raw:
        if isinstance(row, (str, bytes)) or not hasattr(row, "__len__") or len(row) != 2:
            raise ValueError("predict_proba must return two-class probabilities")
        value = float(row[1])
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError("predicted probabilities must be finite and in [0, 1]")
        probabilities.append(value)
    if len(probabilities) != len(x_test):
        raise ValueError("predict_proba result count does not match test rows")
    return tuple(probabilities)


def _seed_for(backend: str, parameters: Mapping[str, Any]) -> int:
    key = "random_seed" if backend == "catboost" else "random_state"
    value = parameters.get(key, 0)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be a non-negative integer")
    return value


def _fold_model_fingerprint(
    *, backend: str,
    parameters: Mapping[str, Any],
    fold_fingerprint: str,
    probabilities: Sequence[float],
) -> str:
    payload = {
        "backend": backend,
        "parameters": dict(parameters),
        "fold_fingerprint": fold_fingerprint,
        "probabilities": [round(value, 15) for value in probabilities],
    }
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()
