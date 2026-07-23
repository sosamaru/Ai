import pytest

from aipro.research.purged_walk_forward import (
    Observation,
    PurgedWalkForwardSplitter,
    WalkForwardConfig,
    assert_no_leakage,
)


def observations(domain="crypto", count=24, horizon=2):
    return [Observation(i, i, i + horizon, domain) for i in range(count)]


def test_builds_deterministic_folds():
    splitter = PurgedWalkForwardSplitter(WalkForwardConfig(8, 4, 4, embargo_size=2))
    first = splitter.split(observations())
    second = splitter.split(observations())
    assert first == second
    assert len(first) == 4


def test_purges_overlapping_training_labels():
    fold = PurgedWalkForwardSplitter(WalkForwardConfig(8, 4, 4)).split(observations())[0]
    assert fold.purged_indices == (6, 7)
    assert_no_leakage(fold, observations())


def test_records_post_test_embargo():
    fold = PurgedWalkForwardSplitter(WalkForwardConfig(8, 4, 4, embargo_size=3)).split(observations())[0]
    assert fold.embargoed_indices == (12, 13, 14)


def test_domains_cannot_be_mixed():
    rows = observations(count=12)
    rows[-1] = Observation(11, 11, 13, "us_stock")
    with pytest.raises(ValueError, match="must not share"):
        PurgedWalkForwardSplitter(WalkForwardConfig(6, 3, 3)).split(rows)


def test_duplicate_indices_are_rejected():
    rows = observations(count=12)
    rows[-1] = Observation(10, 11, 13, "crypto")
    with pytest.raises(ValueError, match="unique"):
        PurgedWalkForwardSplitter(WalkForwardConfig(6, 3, 3)).split(rows)


def test_invalid_label_window_is_rejected():
    rows = observations(count=12)
    rows[0] = Observation(0, 2, 1, "crypto")
    with pytest.raises(ValueError, match="label_end"):
        PurgedWalkForwardSplitter(WalkForwardConfig(6, 3, 3)).split(rows)


def test_configuration_must_produce_a_fold():
    with pytest.raises(ValueError, match="no validation folds"):
        PurgedWalkForwardSplitter(WalkForwardConfig(20, 5, 5)).split(observations(count=10))


def test_rolling_window_respects_max_train_size():
    splitter = PurgedWalkForwardSplitter(
        WalkForwardConfig(6, 3, 3, max_train_size=8, expanding=False)
    )
    folds = splitter.split(observations(count=18, horizon=0))
    assert all(len(fold.train_indices) <= 8 for fold in folds)


def test_fingerprint_changes_with_embargo_evidence():
    no_embargo = PurgedWalkForwardSplitter(WalkForwardConfig(8, 4, 4)).split(observations())[0]
    embargo = PurgedWalkForwardSplitter(WalkForwardConfig(8, 4, 4, embargo_size=1)).split(observations())[0]
    assert no_embargo.fingerprint != embargo.fingerprint
