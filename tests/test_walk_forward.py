from datetime import UTC, datetime, timedelta

import pytest

from aipro.intelligence.walk_forward import (
    LabeledFeatureRow,
    WalkForwardPolicy,
    build_walk_forward_report,
)


def _rows(count: int) -> tuple[LabeledFeatureRow, ...]:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    rows = []
    for index in range(count):
        first = index / 10.0
        second = (index % 7) / 7.0
        target = 0.5 + first * 0.8 - second * 0.2
        rows.append(
            LabeledFeatureRow(
                observed_at_utc=(start + timedelta(hours=index)).isoformat(),
                features=(first, second),
                target_return_pct=target,
                feature_fingerprint=f"{index:064x}",
            )
        )
    return tuple(rows)


def test_builds_deterministic_out_of_sample_folds() -> None:
    policy = WalkForwardPolicy(minimum_train_rows=20, test_rows=5, step_rows=5, embargo_rows=2)
    first = build_walk_forward_report(_rows(42), policy=policy)
    second = build_walk_forward_report(tuple(reversed(_rows(42))), policy=policy)

    assert first.eligible is True
    assert first.fold_count == 4
    assert first.fingerprint == second.fingerprint
    # Keep a bounded regression guard without coupling the test to tiny
    # floating-point or regularization changes in the deterministic baseline.
    assert first.rmse < 0.12
    assert first.directional_accuracy == 1.0
    for fold in first.folds:
        assert datetime.fromisoformat(fold.train_end_utc) < datetime.fromisoformat(fold.test_start_utc)


def test_fails_closed_when_rows_are_insufficient() -> None:
    report = build_walk_forward_report(
        _rows(24),
        policy=WalkForwardPolicy(minimum_train_rows=20, test_rows=5, step_rows=5, embargo_rows=1),
    )
    assert report.eligible is False
    assert report.ineligible_reasons == ("INSUFFICIENT_ROWS",)
    assert report.fold_count == 0


def test_rejects_duplicate_timestamp_or_feature_evidence() -> None:
    rows = list(_rows(26))
    rows[-1] = LabeledFeatureRow(
        observed_at_utc=rows[-2].observed_at_utc,
        features=rows[-1].features,
        target_return_pct=rows[-1].target_return_pct,
        feature_fingerprint=rows[-1].feature_fingerprint,
    )
    with pytest.raises(ValueError, match="duplicate observation"):
        build_walk_forward_report(rows, policy=WalkForwardPolicy(minimum_train_rows=20, test_rows=5))

    rows = list(_rows(26))
    rows[-1] = LabeledFeatureRow(
        observed_at_utc=rows[-1].observed_at_utc,
        features=rows[-1].features,
        target_return_pct=rows[-1].target_return_pct,
        feature_fingerprint=rows[-2].feature_fingerprint,
    )
    with pytest.raises(ValueError, match="duplicate feature"):
        build_walk_forward_report(rows, policy=WalkForwardPolicy(minimum_train_rows=20, test_rows=5))


def test_rejects_mixed_schema_and_width() -> None:
    rows = list(_rows(26))
    rows[-1] = LabeledFeatureRow(
        observed_at_utc=rows[-1].observed_at_utc,
        features=rows[-1].features,
        target_return_pct=rows[-1].target_return_pct,
        feature_fingerprint=rows[-1].feature_fingerprint,
        schema_version="paper-feature-vector-v2",
    )
    with pytest.raises(ValueError, match="mixed feature schemas"):
        build_walk_forward_report(rows, policy=WalkForwardPolicy(minimum_train_rows=20, test_rows=5))

    rows = list(_rows(26))
    rows[-1] = LabeledFeatureRow(
        observed_at_utc=rows[-1].observed_at_utc,
        features=(1.0,),
        target_return_pct=rows[-1].target_return_pct,
        feature_fingerprint=rows[-1].feature_fingerprint,
    )
    with pytest.raises(ValueError, match="inconsistent feature width"):
        build_walk_forward_report(rows, policy=WalkForwardPolicy(minimum_train_rows=20, test_rows=5))
