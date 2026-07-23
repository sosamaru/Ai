from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Iterable, Mapping, Protocol, Sequence


class ModelDomain(str, Enum):
    CRYPTO = "crypto"
    US_STOCK = "us_stock"


class CandidateFamily(str, Enum):
    LOGISTIC = "logistic_regression"
    ELASTIC_NET = "elastic_net"
    RANDOM_FOREST = "random_forest"
    EXTRA_TREES = "extra_trees"
    GRADIENT_BOOSTING = "gradient_boosting"


class CandidateStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABSTAINED = "abstained"


@dataclass(frozen=True)
class CandidateSpec:
    name: str
    family: CandidateFamily
    domain: ModelDomain
    feature_names: tuple[str, ...]
    target_name: str
    random_seed: int
    parameters: Mapping[str, object]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("candidate name is required")
        if not self.feature_names or len(set(self.feature_names)) != len(self.feature_names):
            raise ValueError("feature names must be non-empty and unique")
        if not self.target_name.strip():
            raise ValueError("target name is required")
        if self.random_seed < 0:
            raise ValueError("random_seed must be non-negative")


@dataclass(frozen=True)
class FoldMetrics:
    balanced_accuracy: float
    precision: float
    recall: float
    brier_score: float
    expected_value_bps: float
    turnover: float
    sample_count: int

    def __post_init__(self) -> None:
        for value in (self.balanced_accuracy, self.precision, self.recall):
            if not 0.0 <= value <= 1.0:
                raise ValueError("classification metrics must be in [0, 1]")
        if not 0.0 <= self.brier_score <= 1.0:
            raise ValueError("brier_score must be in [0, 1]")
        if self.turnover < 0.0 or self.sample_count <= 0:
            raise ValueError("turnover must be non-negative and sample_count positive")
        if not math.isfinite(self.expected_value_bps):
            raise ValueError("expected_value_bps must be finite")


@dataclass(frozen=True)
class EvaluationPolicy:
    min_folds: int = 3
    min_samples: int = 300
    min_balanced_accuracy: float = 0.52
    max_brier_score: float = 0.25
    min_expected_value_bps: float = 0.0
    max_metric_std: float = 0.08
    uncertainty_penalty: float = 1.0


@dataclass(frozen=True)
class CandidateEvaluation:
    spec: CandidateSpec
    status: CandidateStatus
    score: float
    mean_balanced_accuracy: float
    mean_brier_score: float
    mean_expected_value_bps: float
    metric_std: float
    total_samples: int
    reasons: tuple[str, ...]
    fingerprint: str


class CandidateAdapter(Protocol):
    @property
    def spec(self) -> CandidateSpec: ...

    def fit(self, x: Sequence[Sequence[float]], y: Sequence[int]) -> None: ...

    def predict_proba(self, x: Sequence[Sequence[float]]) -> Sequence[float]: ...


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _std(values: Sequence[float]) -> float:
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / len(values))


def evaluate_candidate(
    spec: CandidateSpec,
    folds: Iterable[FoldMetrics],
    policy: EvaluationPolicy | None = None,
) -> CandidateEvaluation:
    policy = policy or EvaluationPolicy()
    items = tuple(folds)
    reasons: list[str] = []
    if len(items) < policy.min_folds:
        reasons.append("insufficient_folds")

    total_samples = sum(item.sample_count for item in items)
    if total_samples < policy.min_samples:
        reasons.append("insufficient_samples")

    if not items:
        means = (0.0, 1.0, 0.0)
        metric_std = 1.0
    else:
        accuracies = [item.balanced_accuracy for item in items]
        briers = [item.brier_score for item in items]
        evs = [item.expected_value_bps for item in items]
        means = (_mean(accuracies), _mean(briers), _mean(evs))
        metric_std = _std(accuracies)

    mean_accuracy, mean_brier, mean_ev = means
    if mean_accuracy < policy.min_balanced_accuracy:
        reasons.append("accuracy_below_floor")
    if mean_brier > policy.max_brier_score:
        reasons.append("calibration_above_ceiling")
    if mean_ev <= policy.min_expected_value_bps:
        reasons.append("non_positive_expected_value")
    if metric_std > policy.max_metric_std:
        reasons.append("unstable_across_folds")

    score = (
        mean_accuracy
        - mean_brier
        + mean_ev / 10_000.0
        - policy.uncertainty_penalty * metric_std
    )
    status = CandidateStatus.ACCEPTED if not reasons else CandidateStatus.REJECTED

    payload = {
        "spec": {
            "name": spec.name,
            "family": spec.family.value,
            "domain": spec.domain.value,
            "feature_names": spec.feature_names,
            "target_name": spec.target_name,
            "random_seed": spec.random_seed,
            "parameters": dict(sorted(spec.parameters.items())),
        },
        "status": status.value,
        "score": round(score, 12),
        "means": [round(value, 12) for value in means],
        "metric_std": round(metric_std, 12),
        "total_samples": total_samples,
        "reasons": reasons,
    }
    fingerprint = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return CandidateEvaluation(
        spec=spec,
        status=status,
        score=score,
        mean_balanced_accuracy=mean_accuracy,
        mean_brier_score=mean_brier,
        mean_expected_value_bps=mean_ev,
        metric_std=metric_std,
        total_samples=total_samples,
        reasons=tuple(reasons),
        fingerprint=fingerprint,
    )


def rank_candidates(evaluations: Iterable[CandidateEvaluation], domain: ModelDomain) -> tuple[CandidateEvaluation, ...]:
    items = tuple(evaluations)
    if any(item.spec.domain is not domain for item in items):
        raise ValueError("candidate domains cannot be mixed")
    accepted = [item for item in items if item.status is CandidateStatus.ACCEPTED]
    return tuple(sorted(accepted, key=lambda item: (-item.score, item.spec.name)))
