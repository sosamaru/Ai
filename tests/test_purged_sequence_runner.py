from __future__ import annotations

import math

import pytest

from aipro.intelligence.classical_ml import (
    CandidateFamily,
    EvaluationPolicy,
    ModelDomain,
)
from aipro.intelligence.optional_sequence_backends import SequenceModelSpec
from aipro.research.purged_sequence_runner import (
    SequenceTrainingConfig,
    run_purged_sequence_training,
)
from aipro.research.purged_training_runner import TrainingRow
from aipro.research.purged_walk_forward import WalkForwardConfig


class _FakeTrainer:
    def __init__(self, probability_mode: str = "signal") -> None:
        self.probability_mode = probability_mode
        self.fit_count = 0

    def fit(self, x, y) -> None:
        assert x
        assert len(x) == len(y)
        assert {0, 1}.issubset(set(y))
        self.fit_count += 1

    def predict_proba(self, x):
        if self.probability_mode == "short":
            return [0.5]
        if self.probability_mode == "nan":
            return [math.nan for _ in x]
        return [0.9 if sequence[-1][0] > 0.0 else 0.1 for sequence in x]


def _rows(domain: ModelDomain = ModelDomain.CRYPTO):
    return tuple(
        TrainingRow(
            index=index,
            label_start=index,
            label_end=index,
            domain=domain,
            features=(1.0 if index % 2 else -1.0, float(index)),
            target=index % 2,
            realized_return_bps=15.0 if index % 2 else -10.0,
        )
        for index in range(48)
    )


def _training(**changes):
    values = {
        "spec": SequenceModelSpec(
            name="crypto_lstm_v1",
            domain="crypto",
            model_family="lstm",
            backend="torch",
            feature_names=("signal", "time"),
            target_name="forward_return_positive",
            seed=7,
            parameters={
                "hidden_size": 16,
                "num_layers": 1,
                "dropout": 0.0,
                "sequence_length": 4,
                "batch_size": 8,
                "epochs": 2,
                "learning_rate": 0.001,
            },
        ),
        "decision_threshold": 0.5,
        "estimated_round_trip_cost_bps": 5.0,
    }
    values.update(changes)
    return SequenceTrainingConfig(**values)


def _walk_forward():
    return WalkForwardConfig(
        min_train_size=16,
        test_size=8,
        step_size=8,
        embargo_size=1,
    )


def _policy():
    return EvaluationPolicy(
        min_folds=1,
        min_samples=1,
        min_balanced_accuracy=0.0,
        max_brier_score=1.0,
        min_expected_value_bps=-1000.0,
        max_metric_std=1.0,
    )


def test_sequence_runner_is_deterministic_and_uses_fresh_fold_trainers():
    created = []

    def factory(validated, feature_width):
        assert validated.spec.backend == "torch"
        assert feature_width == 2
        trainer = _FakeTrainer()
        created.append(trainer)
        return trainer

    first = run_purged_sequence_training(
        _rows(),
        feature_names=("signal", "time"),
        walk_forward=_walk_forward(),
        training=_training(),
        evaluation_policy=_policy(),
        trainer_factory=factory,
    )
    first_created = len(created)
    second = run_purged_sequence_training(
        _rows(),
        feature_names=("signal", "time"),
        walk_forward=_walk_forward(),
        training=_training(),
        evaluation_policy=_policy(),
        trainer_factory=factory,
    )

    assert first.fingerprint == second.fingerprint
    assert first.evaluation.fingerprint == second.evaluation.fingerprint
    assert first.evaluation.spec.family is CandidateFamily.SEQUENCE_MODEL
    assert first_created == len(first.folds)
    assert len(created) == len(first.folds) + len(second.folds)
    assert all(trainer.fit_count == 1 for trainer in created)
    assert all(fold.test_count == 5 for fold in first.folds)
    assert first.paper_only is True
    assert first.grants_execution_authority is False


def test_domain_mismatch_fails_before_backend_loading():
    called = False

    def factory(validated, feature_width):
        nonlocal called
        called = True
        return _FakeTrainer()

    with pytest.raises(ValueError, match="domain"):
        run_purged_sequence_training(
            _rows(ModelDomain.US_STOCK),
            feature_names=("signal", "time"),
            walk_forward=_walk_forward(),
            training=_training(),
            trainer_factory=factory,
        )
    assert called is False


def test_feature_identity_must_match_exactly():
    with pytest.raises(ValueError, match="feature_names"):
        run_purged_sequence_training(
            _rows(),
            feature_names=("time", "signal"),
            walk_forward=_walk_forward(),
            training=_training(),
            trainer_factory=lambda validated, width: _FakeTrainer(),
        )


def test_partition_local_sequences_require_sufficient_test_size():
    with pytest.raises(ValueError, match="no contiguous"):
        run_purged_sequence_training(
            _rows(),
            feature_names=("signal", "time"),
            walk_forward=WalkForwardConfig(
                min_train_size=16,
                test_size=3,
                step_size=3,
            ),
            training=_training(),
            trainer_factory=lambda validated, width: _FakeTrainer(),
        )


def test_malformed_probability_count_fails_closed():
    with pytest.raises(ValueError, match="count"):
        run_purged_sequence_training(
            _rows(),
            feature_names=("signal", "time"),
            walk_forward=_walk_forward(),
            training=_training(),
            trainer_factory=lambda validated, width: _FakeTrainer("short"),
        )


def test_non_finite_probability_fails_closed():
    with pytest.raises(ValueError, match="finite"):
        run_purged_sequence_training(
            _rows(),
            feature_names=("signal", "time"),
            walk_forward=_walk_forward(),
            training=_training(),
            trainer_factory=lambda validated, width: _FakeTrainer("nan"),
        )


def test_fold_budget_is_enforced_before_training():
    with pytest.raises(ValueError, match="budget"):
        run_purged_sequence_training(
            _rows(),
            feature_names=("signal", "time"),
            walk_forward=_walk_forward(),
            training=_training(max_test_sequences=4),
            trainer_factory=lambda validated, width: _FakeTrainer(),
        )
