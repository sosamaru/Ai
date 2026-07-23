from datetime import UTC, datetime, timedelta

import pytest

from aipro.intelligence.model_governance import (
    DriftPolicy,
    PaperModelRegistry,
    build_ablation_report,
    build_drift_report,
)
from aipro.intelligence.walk_forward import LabeledFeatureRow, WalkForwardPolicy, build_walk_forward_report


def _rows(count: int, *, shift: float = 0.0, start_hour: int = 0) -> tuple[LabeledFeatureRow, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=start_hour)
    rows = []
    for index in range(count):
        first = index / 10.0 + shift
        second = (index % 7) / 7.0
        target = 0.5 + first * 0.8 - second * 0.2
        rows.append(
            LabeledFeatureRow(
                observed_at_utc=(start + timedelta(hours=index)).isoformat(),
                features=(first, second),
                target_return_pct=target,
                feature_fingerprint=f"{start_hour * 1000 + index:064x}",
            )
        )
    return tuple(rows)


def test_detects_material_feature_drift_deterministically() -> None:
    policy = DriftPolicy(minimum_reference_rows=20, minimum_current_rows=10, z_threshold=1.0, drifted_feature_fraction=0.5)
    first = build_drift_report(_rows(30), _rows(12, shift=10.0, start_hour=100), policy=policy)
    second = build_drift_report(tuple(reversed(_rows(30))), tuple(reversed(_rows(12, shift=10.0, start_hour=100))), policy=policy)
    assert first.eligible is True
    assert first.drifted is True
    assert first.fingerprint == second.fingerprint


def test_drift_fails_closed_for_insufficient_windows() -> None:
    report = build_drift_report(_rows(5), _rows(4, start_hour=100))
    assert report.eligible is False
    assert set(report.ineligible_reasons) == {"INSUFFICIENT_REFERENCE_ROWS", "INSUFFICIENT_CURRENT_ROWS"}


def test_ablation_preserves_out_of_sample_evaluation() -> None:
    policy = WalkForwardPolicy(minimum_train_rows=20, test_rows=5, step_rows=5, embargo_rows=2)
    report = build_ablation_report(_rows(42), policy=policy)
    assert report.feature_count == 2
    assert len(report.results) == 2
    assert all(result.baseline_rmse >= 0 for result in report.results)
    assert len(report.fingerprint) == 64


def test_registry_rejects_duplicates_and_keeps_domains_isolated() -> None:
    policy = WalkForwardPolicy(minimum_train_rows=20, test_rows=5, step_rows=5, embargo_rows=2)
    training = build_walk_forward_report(_rows(42), policy=policy)
    registry = PaperModelRegistry()
    crypto = registry.register(model_id="ridge-v1", asset_domain="crypto", report=training, created_at_utc=datetime(2026, 7, 23, tzinfo=UTC))
    assert crypto.status == "paper_candidate"
    assert registry.list("crypto") == (crypto,)
    assert registry.list("us_stocks") == ()
    with pytest.raises(ValueError, match="already exists"):
        registry.register(model_id="ridge-v1", asset_domain="us_stocks", report=training, created_at_utc=datetime(2026, 7, 23, tzinfo=UTC))
