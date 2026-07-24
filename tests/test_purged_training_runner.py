import pytest

from aipro.intelligence.classical_ml import EvaluationPolicy, ModelDomain
from aipro.research.purged_training_runner import (
    LogisticTrainingConfig,
    TrainingRow,
    run_purged_logistic_training,
)
from aipro.research.purged_walk_forward import WalkForwardConfig


def _rows(domain=ModelDomain.CRYPTO, count=60):
    rows = []
    for index in range(count):
        momentum = ((index % 10) - 5) / 5.0
        trend = (index - count / 2) / count
        target = 1 if momentum + trend > 0 else 0
        realized = 20.0 if target else -15.0
        rows.append(
            TrainingRow(
                index=index,
                label_start=index,
                label_end=index + 2,
                domain=domain,
                features=(momentum, trend),
                target=target,
                realized_return_bps=realized,
            )
        )
    return rows


def _run(rows=None, cost=2.0):
    return run_purged_logistic_training(
        rows or _rows(),
        candidate_name="purged-logistic-v1",
        feature_names=("momentum", "trend"),
        walk_forward=WalkForwardConfig(
            min_train_size=20,
            test_size=10,
            step_size=10,
            embargo_size=2,
        ),
        training=LogisticTrainingConfig(
            learning_rate=0.05,
            epochs=250,
            l2_penalty=0.001,
            estimated_round_trip_cost_bps=cost,
        ),
        evaluation_policy=EvaluationPolicy(
            min_folds=3,
            min_samples=30,
            min_balanced_accuracy=0.50,
            max_brier_score=0.30,
            min_expected_value_bps=0.0,
            max_metric_std=0.30,
        ),
    )


def test_runner_trains_on_purged_folds_and_produces_paper_evidence():
    report = _run()

    assert len(report.folds) == 4
    assert all(item.purged_count == 2 for item in report.folds)
    assert all(item.embargoed_count <= 2 for item in report.folds)
    assert all(len(item.model_fingerprint) == 64 for item in report.folds)
    assert report.paper_only is True
    assert report.grants_execution_authority is False
    assert len(report.fingerprint) == 64


def test_runner_is_deterministic():
    first = _run()
    second = _run(list(reversed(_rows())))

    assert first.fingerprint == second.fingerprint
    assert first.evaluation.fingerprint == second.evaluation.fingerprint
    assert first.folds == second.folds


def test_transaction_cost_reduces_expected_value():
    low_cost = _run(cost=0.0)
    high_cost = _run(cost=12.0)

    assert sum(item.expected_value_bps for item in high_cost.folds) < sum(
        item.expected_value_bps for item in low_cost.folds
    )


def test_crypto_and_us_stock_rows_cannot_be_mixed():
    rows = _rows()
    rows[-1] = TrainingRow(
        index=rows[-1].index,
        label_start=rows[-1].label_start,
        label_end=rows[-1].label_end,
        domain=ModelDomain.US_STOCK,
        features=rows[-1].features,
        target=rows[-1].target,
        realized_return_bps=rows[-1].realized_return_bps,
    )

    with pytest.raises(ValueError, match="cannot be mixed"):
        _run(rows)


def test_feature_width_mismatch_fails_closed():
    rows = _rows()
    bad = rows[0]
    rows[0] = TrainingRow(
        index=bad.index,
        label_start=bad.label_start,
        label_end=bad.label_end,
        domain=bad.domain,
        features=(bad.features[0],),
        target=bad.target,
        realized_return_bps=bad.realized_return_bps,
    )

    with pytest.raises(ValueError, match="feature width"):
        _run(rows)


def test_single_class_dataset_is_rejected():
    rows = [
        TrainingRow(
            index=row.index,
            label_start=row.label_start,
            label_end=row.label_end,
            domain=row.domain,
            features=row.features,
            target=1,
            realized_return_bps=row.realized_return_bps,
        )
        for row in _rows()
    ]

    with pytest.raises(ValueError, match="both target classes"):
        _run(rows)
