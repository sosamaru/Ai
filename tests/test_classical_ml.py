import pytest

from aipro.intelligence.classical_ml import (
    CandidateFamily,
    CandidateSpec,
    CandidateStatus,
    EvaluationPolicy,
    FoldMetrics,
    ModelDomain,
    evaluate_candidate,
    rank_candidates,
)


def spec(name="rf", domain=ModelDomain.CRYPTO):
    return CandidateSpec(
        name=name,
        family=CandidateFamily.RANDOM_FOREST,
        domain=domain,
        feature_names=("return_1h", "volatility"),
        target_name="forward_return_positive",
        random_seed=42,
        parameters={"n_estimators": 100},
    )


def good_folds():
    return [
        FoldMetrics(0.60, 0.61, 0.58, 0.18, 12.0, 0.4, 150),
        FoldMetrics(0.58, 0.60, 0.56, 0.19, 8.0, 0.5, 150),
        FoldMetrics(0.59, 0.59, 0.57, 0.17, 10.0, 0.45, 150),
    ]


def test_accepts_stable_positive_candidate():
    result = evaluate_candidate(spec(), good_folds())
    assert result.status is CandidateStatus.ACCEPTED
    assert result.reasons == ()


def test_rejects_negative_expected_value():
    folds = [FoldMetrics(0.60, 0.60, 0.60, 0.18, -1.0, 0.3, 150) for _ in range(3)]
    result = evaluate_candidate(spec(), folds)
    assert result.status is CandidateStatus.REJECTED
    assert "non_positive_expected_value" in result.reasons


def test_rejects_insufficient_evidence():
    result = evaluate_candidate(spec(), good_folds()[:1])
    assert "insufficient_folds" in result.reasons
    assert "insufficient_samples" in result.reasons


def test_rejects_unstable_candidate():
    folds = [
        FoldMetrics(0.80, 0.70, 0.70, 0.15, 10.0, 0.3, 150),
        FoldMetrics(0.51, 0.50, 0.50, 0.20, 10.0, 0.3, 150),
        FoldMetrics(0.70, 0.65, 0.60, 0.18, 10.0, 0.3, 150),
    ]
    result = evaluate_candidate(spec(), folds, EvaluationPolicy(max_metric_std=0.05))
    assert "unstable_across_folds" in result.reasons


def test_ranking_is_score_first_and_deterministic():
    first = evaluate_candidate(spec("a"), good_folds())
    better = [FoldMetrics(0.62, 0.62, 0.60, 0.16, 14.0, 0.3, 150) for _ in range(3)]
    second = evaluate_candidate(spec("b"), better)
    ranked = rank_candidates([first, second], ModelDomain.CRYPTO)
    assert [item.spec.name for item in ranked] == ["b", "a"]


def test_domain_mixing_fails_closed():
    crypto = evaluate_candidate(spec("c"), good_folds())
    stock = evaluate_candidate(spec("s", ModelDomain.US_STOCK), good_folds())
    with pytest.raises(ValueError):
        rank_candidates([crypto, stock], ModelDomain.CRYPTO)


def test_fingerprint_is_deterministic():
    assert evaluate_candidate(spec(), good_folds()).fingerprint == evaluate_candidate(spec(), good_folds()).fingerprint


def test_invalid_feature_schema_is_rejected():
    with pytest.raises(ValueError):
        CandidateSpec("bad", CandidateFamily.LOGISTIC, ModelDomain.CRYPTO, ("x", "x"), "y", 1, {})
