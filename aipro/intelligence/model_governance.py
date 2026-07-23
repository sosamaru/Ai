from __future__ import annotations

import hashlib
import json
import math
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import fmean, pstdev
from typing import Sequence

from aipro.intelligence.walk_forward import LabeledFeatureRow, WalkForwardPolicy, WalkForwardReport, build_walk_forward_report


@dataclass(frozen=True, slots=True)
class DriftPolicy:
    minimum_reference_rows: int = 20
    minimum_current_rows: int = 10
    z_threshold: float = 1.5
    drifted_feature_fraction: float = 0.25

    def __post_init__(self) -> None:
        if self.minimum_reference_rows < 10 or self.minimum_current_rows < 5:
            raise ValueError("drift windows are too small")
        if self.z_threshold <= 0 or not 0 < self.drifted_feature_fraction <= 1:
            raise ValueError("invalid drift thresholds")


@dataclass(frozen=True, slots=True)
class FeatureDrift:
    feature_index: int
    reference_mean: float
    current_mean: float
    standardized_shift: float
    drifted: bool


@dataclass(frozen=True, slots=True)
class DriftReport:
    schema_version: str
    feature_count: int
    reference_rows: int
    current_rows: int
    drifted_fraction: float
    drifted: bool
    eligible: bool
    ineligible_reasons: tuple[str, ...]
    features: tuple[FeatureDrift, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class AblationResult:
    removed_feature_index: int
    baseline_rmse: float
    ablated_rmse: float
    rmse_delta: float
    baseline_directional_accuracy: float
    ablated_directional_accuracy: float


@dataclass(frozen=True, slots=True)
class AblationReport:
    schema_version: str
    feature_count: int
    baseline_fingerprint: str
    results: tuple[AblationResult, ...]
    fingerprint: str


@dataclass(frozen=True, slots=True)
class PaperModelRecord:
    model_id: str
    asset_domain: str
    schema_version: str
    created_at_utc: str
    training_report_fingerprint: str
    drift_report_fingerprint: str | None
    ablation_report_fingerprint: str | None
    mae: float
    rmse: float
    directional_accuracy: float
    status: str
    fingerprint: str


class PaperModelRegistry:
    def __init__(self) -> None:
        self._records: dict[str, PaperModelRecord] = {}

    def register(
        self,
        *,
        model_id: str,
        asset_domain: str,
        report: WalkForwardReport,
        created_at_utc: datetime,
        drift_report: DriftReport | None = None,
        ablation_report: AblationReport | None = None,
    ) -> PaperModelRecord:
        normalized_id = model_id.strip()
        domain = asset_domain.strip().lower()
        if not normalized_id or domain not in {"crypto", "us_stocks"}:
            raise ValueError("valid model_id and isolated asset_domain are required")
        if normalized_id in self._records:
            raise ValueError("model_id already exists")
        if created_at_utc.tzinfo is None:
            raise ValueError("created_at_utc must be timezone-aware")
        if not report.eligible:
            raise ValueError("ineligible walk-forward report cannot be registered")
        if drift_report is not None and drift_report.schema_version != report.schema_version:
            raise ValueError("drift schema mismatch")
        canonical = {
            "model_id": normalized_id,
            "asset_domain": domain,
            "schema_version": report.schema_version,
            "created_at_utc": created_at_utc.astimezone(UTC).replace(microsecond=0).isoformat(),
            "training_report_fingerprint": report.fingerprint,
            "drift_report_fingerprint": drift_report.fingerprint if drift_report else None,
            "ablation_report_fingerprint": ablation_report.fingerprint if ablation_report else None,
            "mae": report.mae,
            "rmse": report.rmse,
            "directional_accuracy": report.directional_accuracy,
            "status": "paper_candidate",
        }
        fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        record = PaperModelRecord(**canonical, fingerprint=fingerprint)
        self._records[normalized_id] = record
        return record

    def get(self, model_id: str) -> PaperModelRecord:
        return self._records[model_id]

    def list(self, asset_domain: str | None = None) -> tuple[PaperModelRecord, ...]:
        records = self._records.values()
        if asset_domain is not None:
            records = (item for item in records if item.asset_domain == asset_domain.strip().lower())
        return tuple(sorted(records, key=lambda item: (item.created_at_utc, item.model_id)))


def _validate_rows(rows: Sequence[LabeledFeatureRow]) -> tuple[LabeledFeatureRow, ...]:
    ordered = tuple(sorted(rows, key=lambda row: datetime.fromisoformat(row.observed_at_utc)))
    if not ordered:
        return ordered
    schema = ordered[0].schema_version
    width = len(ordered[0].features)
    if any(row.schema_version != schema for row in ordered):
        raise ValueError("mixed feature schemas are not allowed")
    if any(len(row.features) != width for row in ordered):
        raise ValueError("inconsistent feature width")
    return ordered


def build_drift_report(
    reference_rows: Sequence[LabeledFeatureRow],
    current_rows: Sequence[LabeledFeatureRow],
    *,
    policy: DriftPolicy | None = None,
) -> DriftReport:
    active = policy or DriftPolicy()
    reference = _validate_rows(reference_rows)
    current = _validate_rows(current_rows)
    reasons: list[str] = []
    if len(reference) < active.minimum_reference_rows:
        reasons.append("INSUFFICIENT_REFERENCE_ROWS")
    if len(current) < active.minimum_current_rows:
        reasons.append("INSUFFICIENT_CURRENT_ROWS")
    if reference and current and reference[0].schema_version != current[0].schema_version:
        raise ValueError("reference and current schemas differ")
    if reference and current and len(reference[0].features) != len(current[0].features):
        raise ValueError("reference and current feature widths differ")
    schema = reference[0].schema_version if reference else current[0].schema_version if current else "unknown"
    width = len(reference[0].features) if reference else len(current[0].features) if current else 0
    features: list[FeatureDrift] = []
    if not reasons:
        for index in range(width):
            reference_values = [row.features[index] for row in reference]
            current_values = [row.features[index] for row in current]
            reference_mean = fmean(reference_values)
            current_mean = fmean(current_values)
            scale = pstdev(reference_values)
            shift = abs(current_mean - reference_mean) / max(scale, 1e-12)
            features.append(FeatureDrift(index, round(reference_mean, 8), round(current_mean, 8), round(shift, 8), shift >= active.z_threshold))
    drifted_fraction = (sum(item.drifted for item in features) / len(features)) if features else 0.0
    canonical = {
        "schema_version": schema,
        "reference_fingerprints": [row.feature_fingerprint for row in reference],
        "current_fingerprints": [row.feature_fingerprint for row in current],
        "policy": asdict(active),
        "features": [asdict(item) for item in features],
        "eligible": not reasons,
        "ineligible_reasons": sorted(set(reasons)),
    }
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return DriftReport(schema, width, len(reference), len(current), round(drifted_fraction, 8), drifted_fraction >= active.drifted_feature_fraction, not reasons, tuple(sorted(set(reasons))), tuple(features), fingerprint)


def build_ablation_report(
    rows: Sequence[LabeledFeatureRow], *, policy: WalkForwardPolicy | None = None
) -> AblationReport:
    ordered = _validate_rows(rows)
    baseline = build_walk_forward_report(ordered, policy=policy)
    if not baseline.eligible:
        raise ValueError("eligible baseline walk-forward report is required")
    results: list[AblationResult] = []
    for index in range(baseline.feature_count):
        ablated_rows = tuple(
            LabeledFeatureRow(
                observed_at_utc=row.observed_at_utc,
                features=row.features[:index] + row.features[index + 1 :],
                target_return_pct=row.target_return_pct,
                feature_fingerprint=hashlib.sha256(f"{row.feature_fingerprint}:{index}".encode()).hexdigest(),
                schema_version=row.schema_version,
            )
            for row in ordered
        )
        report = build_walk_forward_report(ablated_rows, policy=policy)
        results.append(AblationResult(index, baseline.rmse, report.rmse, round(report.rmse - baseline.rmse, 8), baseline.directional_accuracy, report.directional_accuracy))
    canonical = {"schema_version": baseline.schema_version, "baseline_fingerprint": baseline.fingerprint, "results": [asdict(item) for item in results]}
    fingerprint = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return AblationReport(baseline.schema_version, baseline.feature_count, baseline.fingerprint, tuple(results), fingerprint)


__all__ = ["AblationReport", "AblationResult", "DriftPolicy", "DriftReport", "FeatureDrift", "PaperModelRecord", "PaperModelRegistry", "build_ablation_report", "build_drift_report"]
