"""Deterministic PAPER-only training runner with purged walk-forward validation.

The runner trains a small standard-library logistic classifier independently on
purged folds. It never persists a model, contacts a broker, submits an order, or
grants PAPER/LIVE execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import math
from typing import Iterable, Sequence

from aipro.intelligence.classical_ml import (
    CandidateEvaluation,
    CandidateFamily,
    CandidateSpec,
    EvaluationPolicy,
    FoldMetrics,
    ModelDomain,
    evaluate_candidate,
)
from aipro.research.purged_walk_forward import (
    Observation,
    PurgedWalkForwardSplitter,
    WalkForwardConfig,
    assert_no_leakage,
)


@dataclass(frozen=True)
class TrainingRow:
    index: int
    label_start: int
    label_end: int
    domain: ModelDomain
    features: tuple[float, ...]
    target: int
    realized_return_bps: float

    def __post_init__(self) -> None:
        if self.index < 0:
            raise ValueError("index must be non-negative")
        if self.label_start < 0 or self.label_end < self.label_start:
            raise ValueError("invalid label window")
        if not self.features:
            raise ValueError("features cannot be empty")
        if any(not math.isfinite(value) for value in self.features):
            raise ValueError("features must be finite")
        if self.target not in (0, 1):
            raise ValueError("target must be binary")
        if not math.isfinite(self.realized_return_bps):
            raise ValueError("realized_return_bps must be finite")


@dataclass(frozen=True)
class LogisticTrainingConfig:
    learning_rate: float = 0.05
    epochs: int = 200
    l2_penalty: float = 0.001
    decision_threshold: float = 0.5
    estimated_round_trip_cost_bps: float = 5.0

    def __post_init__(self) -> None:
        if not 0.0 < self.learning_rate <= 1.0:
            raise ValueError("learning_rate must be in (0, 1]")
        if not 1 <= self.epochs <= 5000:
            raise ValueError("epochs must be in [1, 5000]")
        if not 0.0 <= self.l2_penalty <= 1.0:
            raise ValueError("l2_penalty must be in [0, 1]")
        if not 0.0 < self.decision_threshold < 1.0:
            raise ValueError("decision_threshold must be in (0, 1)")
        if self.estimated_round_trip_cost_bps < 0.0:
            raise ValueError("estimated_round_trip_cost_bps must be non-negative")


@dataclass(frozen=True)
class PurgedFoldTrainingEvidence:
    fold_fingerprint: str
    train_count: int
    test_count: int
    purged_count: int
    embargoed_count: int
    balanced_accuracy: float
    brier_score: float
    expected_value_bps: float
    turnover: float
    model_fingerprint: str


@dataclass(frozen=True)
class PurgedTrainingReport:
    domain: ModelDomain
    candidate_name: str
    folds: tuple[PurgedFoldTrainingEvidence, ...]
    evaluation: CandidateEvaluation
    fingerprint: str
    paper_only: bool = True
    grants_execution_authority: bool = False


def run_purged_logistic_training(
    rows: Sequence[TrainingRow],
    *,
    candidate_name: str,
    feature_names: Sequence[str],
    walk_forward: WalkForwardConfig,
    training: LogisticTrainingConfig | None = None,
    evaluation_policy: EvaluationPolicy | None = None,
) -> PurgedTrainingReport:
    """Train and score one deterministic logistic candidate across purged folds."""

    training = training or LogisticTrainingConfig()
    ordered = _validate_rows(rows, feature_names)
    domain = ordered[0].domain
    splitter = PurgedWalkForwardSplitter(walk_forward)
    observations = tuple(
        Observation(row.index, row.label_start, row.label_end, row.domain.value)
        for row in ordered
    )
    folds = splitter.split(observations)
    by_index = {row.index: row for row in ordered}
    evidence: list[PurgedFoldTrainingEvidence] = []
    metrics: list[FoldMetrics] = []

    for fold in folds:
        assert_no_leakage(fold, observations)
        train_rows = tuple(by_index[index] for index in fold.train_indices)
        test_rows = tuple(by_index[index] for index in fold.test_indices)
        means, scales = _fit_scaler(train_rows)
        x_train = tuple(_scale(row.features, means, scales) for row in train_rows)
        x_test = tuple(_scale(row.features, means, scales) for row in test_rows)
        weights, bias = _fit_logistic(x_train, tuple(row.target for row in train_rows), training)
        probabilities = tuple(_sigmoid(_dot(weights, vector) + bias) for vector in x_test)
        fold_metrics = _score_fold(test_rows, probabilities, training)
        metrics.append(fold_metrics)
        model_fingerprint = _model_fingerprint(weights, bias, means, scales, training)
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
        family=CandidateFamily.LOGISTIC,
        domain=domain,
        feature_names=tuple(feature_names),
        target_name="forward_return_positive",
        random_seed=0,
        parameters={
            "learning_rate": training.learning_rate,
            "epochs": training.epochs,
            "l2_penalty": training.l2_penalty,
            "decision_threshold": training.decision_threshold,
            "estimated_round_trip_cost_bps": training.estimated_round_trip_cost_bps,
            "validation": "purged_walk_forward",
        },
    )
    evaluation = evaluate_candidate(spec, metrics, evaluation_policy)
    payload = {
        "domain": domain.value,
        "candidate_name": candidate_name,
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


def _validate_rows(rows: Sequence[TrainingRow], feature_names: Sequence[str]) -> tuple[TrainingRow, ...]:
    if not rows:
        raise ValueError("rows cannot be empty")
    names = tuple(feature_names)
    if not names or len(names) != len(set(names)):
        raise ValueError("feature_names must be non-empty and unique")
    ordered = tuple(sorted(rows, key=lambda row: row.index))
    if len({row.index for row in ordered}) != len(ordered):
        raise ValueError("row indices must be unique")
    domains = {row.domain for row in ordered}
    if len(domains) != 1:
        raise ValueError("crypto and US-stock rows cannot be mixed")
    width = len(names)
    if any(len(row.features) != width for row in ordered):
        raise ValueError("feature width does not match feature_names")
    if len({row.target for row in ordered}) < 2:
        raise ValueError("both target classes are required")
    return ordered


def _fit_scaler(rows: Sequence[TrainingRow]) -> tuple[tuple[float, ...], tuple[float, ...]]:
    width = len(rows[0].features)
    means = tuple(sum(row.features[i] for row in rows) / len(rows) for i in range(width))
    scales = []
    for i, mean in enumerate(means):
        variance = sum((row.features[i] - mean) ** 2 for row in rows) / len(rows)
        scales.append(max(math.sqrt(variance), 1e-12))
    return means, tuple(scales)


def _scale(values: Sequence[float], means: Sequence[float], scales: Sequence[float]) -> tuple[float, ...]:
    return tuple((value - mean) / scale for value, mean, scale in zip(values, means, scales))


def _fit_logistic(
    x: Sequence[Sequence[float]],
    y: Sequence[int],
    config: LogisticTrainingConfig,
) -> tuple[tuple[float, ...], float]:
    weights = [0.0] * len(x[0])
    bias = 0.0
    count = float(len(x))
    for _ in range(config.epochs):
        gradient = [0.0] * len(weights)
        bias_gradient = 0.0
        for vector, target in zip(x, y):
            error = _sigmoid(_dot(weights, vector) + bias) - target
            for index, value in enumerate(vector):
                gradient[index] += error * value
            bias_gradient += error
        for index in range(len(weights)):
            regularized = gradient[index] / count + config.l2_penalty * weights[index]
            weights[index] -= config.learning_rate * regularized
        bias -= config.learning_rate * bias_gradient / count
    return tuple(weights), bias


def _score_fold(
    rows: Sequence[TrainingRow],
    probabilities: Sequence[float],
    config: LogisticTrainingConfig,
) -> FoldMetrics:
    predictions = tuple(probability >= config.decision_threshold for probability in probabilities)
    positives = [index for index, row in enumerate(rows) if row.target == 1]
    negatives = [index for index, row in enumerate(rows) if row.target == 0]
    sensitivity = sum(predictions[i] for i in positives) / len(positives) if positives else 0.0
    specificity = sum(not predictions[i] for i in negatives) / len(negatives) if negatives else 0.0
    balanced_accuracy = (sensitivity + specificity) / 2.0
    true_positive = sum(predictions[i] and rows[i].target == 1 for i in range(len(rows)))
    predicted_positive = sum(predictions)
    precision = true_positive / predicted_positive if predicted_positive else 0.0
    recall = sensitivity
    brier = sum((probability - row.target) ** 2 for row, probability in zip(rows, probabilities)) / len(rows)
    selected_returns = [
        row.realized_return_bps - config.estimated_round_trip_cost_bps
        for row, selected in zip(rows, predictions)
        if selected
    ]
    expected_value = sum(selected_returns) / len(selected_returns) if selected_returns else 0.0
    turnover = predicted_positive / len(rows)
    return FoldMetrics(
        balanced_accuracy=balanced_accuracy,
        precision=precision,
        recall=recall,
        brier_score=brier,
        expected_value_bps=expected_value,
        turnover=turnover,
        sample_count=len(rows),
    )


def _sigmoid(value: float) -> float:
    if value >= 0:
        exp_value = math.exp(-value)
        return 1.0 / (1.0 + exp_value)
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def _dot(left: Sequence[float], right: Sequence[float]) -> float:
    return sum(a * b for a, b in zip(left, right))


def _model_fingerprint(
    weights: Sequence[float],
    bias: float,
    means: Sequence[float],
    scales: Sequence[float],
    config: LogisticTrainingConfig,
) -> str:
    payload = {
        "weights": [round(value, 15) for value in weights],
        "bias": round(bias, 15),
        "means": [round(value, 15) for value in means],
        "scales": [round(value, 15) for value in scales],
        "config": config.__dict__,
    }
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
