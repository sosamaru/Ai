from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from datetime import datetime
from statistics import fmean
from typing import Sequence


@dataclass(frozen=True, slots=True)
class LabeledFeatureRow:
    observed_at_utc: str
    features: tuple[float, ...]
    target_return_pct: float
    feature_fingerprint: str
    schema_version: str = "paper-feature-vector-v1"

    def __post_init__(self) -> None:
        observed = datetime.fromisoformat(self.observed_at_utc)
        if observed.tzinfo is None:
            raise ValueError("observed_at_utc must be timezone-aware")
        if not self.features:
            raise ValueError("features are required")
        if any(not math.isfinite(value) for value in (*self.features, self.target_return_pct)):
            raise ValueError("features and target must be finite")
        if len(self.feature_fingerprint) != 64:
            raise ValueError("feature_fingerprint must be a SHA-256 digest")
        if not self.schema_version.strip():
            raise ValueError("schema_version is required")


@dataclass(frozen=True, slots=True)
class WalkForwardPolicy:
    minimum_train_rows: int = 60
    test_rows: int = 20
    step_rows: int = 20
    embargo_rows: int = 1
    ridge_alpha: float = 1.0

    def __post_init__(self) -> None:
        if self.minimum_train_rows < 20:
            raise ValueError("minimum_train_rows must be at least 20")
        if self.test_rows <= 0 or self.step_rows <= 0 or self.embargo_rows < 0:
            raise ValueError("invalid walk-forward window sizes")
        if self.ridge_alpha < 0:
            raise ValueError("ridge_alpha must be non-negative")


@dataclass(frozen=True, slots=True)
class WalkForwardFold:
    train_start_utc: str
    train_end_utc: str
    test_start_utc: str
    test_end_utc: str
    train_rows: int
    test_rows: int
    mae: float
    rmse: float
    directional_accuracy: float
    predictions: tuple[float, ...]
    targets: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class WalkForwardReport:
    schema_version: str
    feature_count: int
    row_count: int
    fold_count: int
    mae: float
    rmse: float
    directional_accuracy: float
    eligible: bool
    ineligible_reasons: tuple[str, ...]
    folds: tuple[WalkForwardFold, ...]
    fingerprint: str


def _solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("singular training matrix")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            augmented[row] = [
                augmented[row][index] - factor * augmented[column][index]
                for index in range(size + 1)
            ]
    return [augmented[index][-1] for index in range(size)]


def _fit_ridge(rows: Sequence[LabeledFeatureRow], alpha: float) -> tuple[float, ...]:
    width = len(rows[0].features) + 1
    gram = [[0.0 for _ in range(width)] for _ in range(width)]
    rhs = [0.0 for _ in range(width)]
    for row in rows:
        values = (1.0, *row.features)
        for i in range(width):
            rhs[i] += values[i] * row.target_return_pct
            for j in range(width):
                gram[i][j] += values[i] * values[j]
    for index in range(1, width):
        gram[index][index] += alpha
    return tuple(_solve(gram, rhs))


def _predict(weights: Sequence[float], features: Sequence[float]) -> float:
    return weights[0] + sum(weight * value for weight, value in zip(weights[1:], features, strict=True))


def build_walk_forward_report(
    rows: Sequence[LabeledFeatureRow], *, policy: WalkForwardPolicy | None = None
) -> WalkForwardReport:
    active = policy or WalkForwardPolicy()
    ordered = tuple(sorted(rows, key=lambda row: datetime.fromisoformat(row.observed_at_utc)))
    reasons: list[str] = []
    if not ordered:
        reasons.append("NO_ROWS")
        schema = "unknown"
        feature_count = 0
    else:
        schema = ordered[0].schema_version
        feature_count = len(ordered[0].features)
        if len({row.observed_at_utc for row in ordered}) != len(ordered):
            raise ValueError("duplicate observation timestamps are not allowed")
        if len({row.feature_fingerprint for row in ordered}) != len(ordered):
            raise ValueError("duplicate feature fingerprints are not allowed")
        if any(row.schema_version != schema for row in ordered):
            raise ValueError("mixed feature schemas are not allowed")
        if any(len(row.features) != feature_count for row in ordered):
            raise ValueError("inconsistent feature width")
        required = active.minimum_train_rows + active.embargo_rows + active.test_rows
        if len(ordered) < required:
            reasons.append("INSUFFICIENT_ROWS")

    folds: list[WalkForwardFold] = []
    train_end = active.minimum_train_rows
    while train_end + active.embargo_rows + active.test_rows <= len(ordered):
        train = ordered[:train_end]
        test_start = train_end + active.embargo_rows
        test = ordered[test_start : test_start + active.test_rows]
        if datetime.fromisoformat(train[-1].observed_at_utc) >= datetime.fromisoformat(test[0].observed_at_utc):
            raise ValueError("training data must precede test data")
        weights = _fit_ridge(train, active.ridge_alpha)
        predictions = tuple(_predict(weights, row.features) for row in test)
        targets = tuple(row.target_return_pct for row in test)
        errors = tuple(prediction - target for prediction, target in zip(predictions, targets, strict=True))
        mae = fmean(abs(error) for error in errors)
        rmse = math.sqrt(fmean(error * error for error in errors))
        directional = fmean(
            1.0 if (prediction >= 0) == (target >= 0) else 0.0
            for prediction, target in zip(predictions, targets, strict=True)
        )
        folds.append(
            WalkForwardFold(
                train_start_utc=train[0].observed_at_utc,
                train_end_utc=train[-1].observed_at_utc,
                test_start_utc=test[0].observed_at_utc,
                test_end_utc=test[-1].observed_at_utc,
                train_rows=len(train),
                test_rows=len(test),
                mae=round(mae, 8),
                rmse=round(rmse, 8),
                directional_accuracy=round(directional, 8),
                predictions=tuple(round(value, 8) for value in predictions),
                targets=tuple(round(value, 8) for value in targets),
            )
        )
        train_end += active.step_rows

    if not folds and not reasons:
        reasons.append("NO_VALID_FOLDS")
    all_predictions = tuple(value for fold in folds for value in fold.predictions)
    all_targets = tuple(value for fold in folds for value in fold.targets)
    if all_predictions:
        errors = tuple(prediction - target for prediction, target in zip(all_predictions, all_targets, strict=True))
        mae = fmean(abs(error) for error in errors)
        rmse = math.sqrt(fmean(error * error for error in errors))
        directional = fmean(
            1.0 if (prediction >= 0) == (target >= 0) else 0.0
            for prediction, target in zip(all_predictions, all_targets, strict=True)
        )
    else:
        mae = rmse = directional = 0.0

    canonical = {
        "schema_version": schema,
        "feature_count": feature_count,
        "row_fingerprints": [row.feature_fingerprint for row in ordered],
        "policy": {
            "minimum_train_rows": active.minimum_train_rows,
            "test_rows": active.test_rows,
            "step_rows": active.step_rows,
            "embargo_rows": active.embargo_rows,
            "ridge_alpha": active.ridge_alpha,
        },
        "folds": [
            {
                "train_start_utc": fold.train_start_utc,
                "train_end_utc": fold.train_end_utc,
                "test_start_utc": fold.test_start_utc,
                "test_end_utc": fold.test_end_utc,
                "predictions": fold.predictions,
                "targets": fold.targets,
            }
            for fold in folds
        ],
        "eligible": not reasons,
        "ineligible_reasons": sorted(set(reasons)),
    }
    fingerprint = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return WalkForwardReport(
        schema_version=schema,
        feature_count=feature_count,
        row_count=len(ordered),
        fold_count=len(folds),
        mae=round(mae, 8),
        rmse=round(rmse, 8),
        directional_accuracy=round(directional, 8),
        eligible=not reasons,
        ineligible_reasons=tuple(sorted(set(reasons))),
        folds=tuple(folds),
        fingerprint=fingerprint,
    )


__all__ = [
    "LabeledFeatureRow",
    "WalkForwardFold",
    "WalkForwardPolicy",
    "WalkForwardReport",
    "build_walk_forward_report",
]
