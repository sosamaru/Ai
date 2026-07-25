import pytest

from aipro.intelligence.challenger_monitor import (
    ModelHealthSnapshot,
    MonitoringPolicy,
    Recommendation,
    assess_challenger,
)
from aipro.intelligence.classical_ml import ModelDomain


def _snapshot(name: str, **changes):
    values = {
        "domain": ModelDomain.CRYPTO,
        "candidate_name": name,
        "candidate_fingerprint": ("a" if name == "champion" else "b") * 64,
        "evaluation_fingerprint": ("c" if name == "champion" else "d") * 64,
        "score": 0.45 if name == "champion" else 0.48,
        "drift_score": 0.10,
        "brier_score": 0.18,
        "expected_value_bps": 10.0 if name == "champion" else 14.0,
        "drawdown_pct": 3.0,
        "observation_count": 500,
    }
    values.update(changes)
    return ModelHealthSnapshot(**values)


def test_decisively_better_challenger_requires_review_not_auto_promotion():
    decision = assess_challenger(_snapshot("champion"), _snapshot("challenger"))

    assert decision.recommendation is Recommendation.REVIEW_REPLACEMENT
    assert decision.reasons == ("challenger_decisively_better",)
    assert decision.paper_only is True


def test_non_positive_champion_ev_recommends_deactivation():
    decision = assess_challenger(
        _snapshot("champion", expected_value_bps=-1.0),
        _snapshot("challenger"),
    )

    assert decision.recommendation is Recommendation.DEACTIVATE
    assert "champion_non_positive_expected_value" in decision.reasons


def test_excessive_drawdown_recommends_deactivation():
    decision = assess_challenger(
        _snapshot("champion", drawdown_pct=12.0),
        None,
        MonitoringPolicy(max_drawdown_pct=10.0),
    )

    assert decision.recommendation is Recommendation.DEACTIVATE
    assert "champion_drawdown_exceeded" in decision.reasons


def test_drift_without_healthy_challenger_recommends_rollback_review():
    decision = assess_challenger(
        _snapshot("champion", drift_score=0.30),
        _snapshot("challenger", brier_score=0.40),
    )

    assert decision.recommendation is Recommendation.REVIEW_ROLLBACK
    assert "champion_drift_exceeded" in decision.reasons
    assert "challenger_health_gate_failed" in decision.reasons


def test_insufficient_challenger_evidence_cannot_replace():
    decision = assess_challenger(
        _snapshot("champion"),
        _snapshot("challenger", observation_count=50),
    )

    assert decision.recommendation is Recommendation.HOLD
    assert "insufficient_challenger_observations" in decision.reasons


def test_domain_mixing_fails_closed():
    with pytest.raises(ValueError, match="domains"):
        assess_challenger(
            _snapshot("champion"),
            _snapshot("challenger", domain=ModelDomain.US_STOCK),
        )


def test_same_candidate_cannot_challenge_itself():
    champion = _snapshot("champion")
    with pytest.raises(ValueError, match="differ"):
        assess_challenger(
            champion,
            _snapshot("challenger", candidate_fingerprint=champion.candidate_fingerprint),
        )


def test_fingerprint_is_deterministic():
    champion = _snapshot("champion")
    challenger = _snapshot("challenger")

    assert assess_challenger(champion, challenger).fingerprint == assess_challenger(
        champion, challenger
    ).fingerprint
