import pytest

from aipro.intelligence.domain_regime import (
    Domain,
    DomainStrategyPipeline,
    Regime,
    RegimeFeatures,
    StrategyCandidate,
    classify_regime,
)


def features(domain=Domain.CRYPTO, **overrides):
    values = dict(
        domain=domain,
        trend_return=0.05,
        realized_volatility=0.3,
        volatility_zscore=0.2,
        drawdown=-0.03,
        breadth=0.4,
        momentum=0.5,
        liquidity_stress=0.1,
    )
    values.update(overrides)
    return RegimeFeatures(**values)


def candidate(name="trend", domain=Domain.CRYPTO, regimes=frozenset({Regime.TREND_UP}), ev=0.02, uncertainty=0.2):
    return StrategyCandidate(
        name=name,
        supported_domains=frozenset({domain}),
        supported_regimes=regimes,
        expected_value=ev,
        uncertainty=uncertainty,
    )


def test_classifies_uptrend():
    decision = classify_regime(features())
    assert decision.regime is Regime.TREND_UP
    assert decision.confidence > 0
    assert len(decision.fingerprint) == 64


def test_risk_off_has_priority_over_trend():
    decision = classify_regime(features(drawdown=-0.2, liquidity_stress=0.85))
    assert decision.regime is Regime.RISK_OFF


def test_high_volatility_classification():
    decision = classify_regime(features(volatility_zscore=2.5))
    assert decision.regime is Regime.HIGH_VOLATILITY


def test_pipeline_selects_highest_uncertainty_adjusted_ev():
    pipeline = DomainStrategyPipeline(
        Domain.CRYPTO,
        [
            candidate(name="high_raw", ev=0.03, uncertainty=0.8),
            candidate(name="stable", ev=0.02, uncertainty=0.1),
        ],
    )
    _, selection = pipeline.evaluate(features())
    assert selection.selected_strategy == "stable"
    assert selection.abstained is False


def test_pipeline_abstains_when_regime_is_unknown():
    pipeline = DomainStrategyPipeline(Domain.CRYPTO, [candidate()])
    _, selection = pipeline.evaluate(features(trend_return=0.01, momentum=0.5, volatility_zscore=0.0))
    assert selection.abstained is True


def test_foreign_domain_candidate_is_rejected():
    with pytest.raises(ValueError, match="foreign-domain"):
        DomainStrategyPipeline(Domain.CRYPTO, [candidate(domain=Domain.US_STOCK)])


def test_foreign_domain_features_are_rejected():
    pipeline = DomainStrategyPipeline(Domain.CRYPTO, [candidate()])
    with pytest.raises(ValueError, match="feature domain mismatch"):
        pipeline.evaluate(features(domain=Domain.US_STOCK))


def test_invalid_nonfinite_feature_fails_closed():
    with pytest.raises(ValueError, match="finite"):
        classify_regime(features(momentum=float("nan")))


def test_deterministic_fingerprints():
    pipeline = DomainStrategyPipeline(Domain.CRYPTO, [candidate()])
    first = pipeline.evaluate(features())
    second = pipeline.evaluate(features())
    assert first[0].fingerprint == second[0].fingerprint
    assert first[1].fingerprint == second[1].fingerprint
