import pytest

from aipro.intelligence.classical_ml import (
    CandidateFamily,
    CandidateSpec,
    FoldMetrics,
    ModelDomain,
    evaluate_candidate,
)
from aipro.intelligence.model_champion import ChampionPolicy, select_champion


def _spec(name: str, domain: ModelDomain = ModelDomain.CRYPTO) -> CandidateSpec:
    return CandidateSpec(
        name=name,
        family=CandidateFamily.RANDOM_FOREST,
        domain=domain,
        feature_names=("return_1h", "volatility"),
        target_name="forward_return_positive",
        random_seed=42,
        parameters={"n_estimators": 100},
    )


def _evaluation(name: str, accuracy: float, brier: float, ev_bps: float):
    folds = [
        FoldMetrics(accuracy, 0.60, 0.58, brier, ev_bps, 0.4, 150)
        for _ in range(3)
    ]
    return evaluate_candidate(_spec(name), folds)


def test_selects_decisive_paper_champion():
    champion = _evaluation("champion", 0.64, 0.15, 18.0)
    challenger = _evaluation("challenger", 0.56, 0.20, 8.0)

    decision = select_champion([challenger, champion], ModelDomain.CRYPTO)

    assert decision.approved is True
    assert decision.champion.spec.name == "champion"
    assert decision.challenger.spec.name == "challenger"
    assert decision.paper_only is True
    assert len(decision.fingerprint) == 64


def test_indecisive_margin_fails_closed():
    first = _evaluation("a", 0.60, 0.18, 10.0)
    second = _evaluation("b", 0.599, 0.18, 9.5)

    decision = select_champion(
        [first, second],
        ModelDomain.CRYPTO,
        ChampionPolicy(min_score_margin=0.01, min_expected_value_margin_bps=1.0),
    )

    assert decision.approved is False
    assert "insufficient_score_margin" in decision.reasons
    assert "insufficient_expected_value_margin" in decision.reasons


def test_rejected_candidates_are_not_eligible():
    rejected = _evaluation("negative-ev", 0.60, 0.18, -2.0)

    decision = select_champion([rejected], ModelDomain.CRYPTO)

    assert decision.approved is False
    assert decision.champion is None
    assert decision.reasons == ("no_eligible_candidate",)


def test_domain_mixing_is_rejected():
    crypto = _evaluation("crypto", 0.62, 0.16, 15.0)
    stock_spec = _spec("stock", ModelDomain.US_STOCK)
    stock = evaluate_candidate(
        stock_spec,
        [FoldMetrics(0.62, 0.60, 0.58, 0.16, 15.0, 0.4, 150) for _ in range(3)],
    )

    with pytest.raises(ValueError, match="domains"):
        select_champion([crypto, stock], ModelDomain.CRYPTO)


def test_duplicate_candidate_names_are_rejected():
    candidate = _evaluation("same", 0.62, 0.16, 15.0)

    with pytest.raises(ValueError, match="unique"):
        select_champion([candidate, candidate], ModelDomain.CRYPTO)


def test_fingerprint_is_deterministic():
    evaluations = [
        _evaluation("champion", 0.64, 0.15, 18.0),
        _evaluation("challenger", 0.56, 0.20, 8.0),
    ]

    assert (
        select_champion(evaluations, ModelDomain.CRYPTO).fingerprint
        == select_champion(evaluations, ModelDomain.CRYPTO).fingerprint
    )
