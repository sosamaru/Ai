from unittest.mock import patch

import pytest

from aipro.intelligence.classical_ml import EvaluationPolicy, ModelDomain
from aipro.research.purged_boosting_runner import (
    BoostingTrainingConfig,
    run_purged_boosting_training,
)
from aipro.research.purged_training_runner import TrainingRow
from aipro.research.purged_walk_forward import WalkForwardConfig


class _FakeEstimator:
    def fit(self, x, y):
        self.fitted = (tuple(x), tuple(y))
        return self

    def predict_proba(self, x):
        return tuple((1.0 - min(max(row[0], 0.0), 1.0), min(max(row[0], 0.0), 1.0)) for row in x)


def _rows(domain=ModelDomain.CRYPTO):
    return tuple(
        TrainingRow(
            index=index,
            label_start=index,
            label_end=index,
            domain=domain,
            features=(0.9 if index % 2 else 0.1, float(index)),
            target=index % 2,
            realized_return_bps=12.0 if index % 2 else -8.0,
        )
        for index in range(12)
    )


def _policy():
    return EvaluationPolicy(
        min_folds=3,
        min_samples=6,
        min_balanced_accuracy=0.5,
        max_brier_score=0.5,
        min_expected_value_bps=0.0,
        max_metric_std=1.0,
    )


def test_runs_optional_backend_on_purged_folds():
    with patch(
        "aipro.research.purged_boosting_runner.build_backend",
        side_effect=lambda name, parameters: _FakeEstimator(),
    ) as builder:
        report = run_purged_boosting_training(
            _rows(),
            candidate_name="crypto_xgb_v1",
            feature_names=("signal", "time"),
            walk_forward=WalkForwardConfig(min_train_size=6, test_size=2, step_size=2, embargo_size=1),
            training=BoostingTrainingConfig(
                backend="xgboost",
                parameters={"n_estimators": 20, "random_state": 7},
            ),
            evaluation_policy=_policy(),
        )

    assert report.domain is ModelDomain.CRYPTO
    assert report.paper_only is True
    assert report.grants_execution_authority is False
    assert len(report.folds) == 3
    assert builder.call_count == 3
    assert report.evaluation.spec.parameters["backend"] == "xgboost"
    assert report.evaluation.spec.random_seed == 7
    assert len(report.fingerprint) == 64


def test_mixed_domains_fail_closed_before_backend_load():
    rows = list(_rows())
    rows[-1] = TrainingRow(
        index=rows[-1].index,
        label_start=rows[-1].label_start,
        label_end=rows[-1].label_end,
        domain=ModelDomain.US_STOCK,
        features=rows[-1].features,
        target=rows[-1].target,
        realized_return_bps=rows[-1].realized_return_bps,
    )
    with patch("aipro.research.purged_boosting_runner.build_backend") as builder:
        with pytest.raises(ValueError, match="cannot be mixed"):
            run_purged_boosting_training(
                rows,
                candidate_name="invalid",
                feature_names=("signal", "time"),
                walk_forward=WalkForwardConfig(min_train_size=6, test_size=2, step_size=2),
                training=BoostingTrainingConfig(backend="lightgbm"),
            )
    builder.assert_not_called()


def test_invalid_probability_shape_is_rejected():
    estimator = _FakeEstimator()
    estimator.predict_proba = lambda x: (0.5 for _ in x)
    with patch("aipro.research.purged_boosting_runner.build_backend", return_value=estimator):
        with pytest.raises(ValueError, match="two-class"):
            run_purged_boosting_training(
                _rows(),
                candidate_name="bad_probability",
                feature_names=("signal", "time"),
                walk_forward=WalkForwardConfig(min_train_size=6, test_size=2, step_size=2),
                training=BoostingTrainingConfig(backend="catboost"),
            )


def test_unknown_backend_is_rejected():
    with pytest.raises(ValueError, match="unsupported boosting backend"):
        BoostingTrainingConfig(backend="combined")
