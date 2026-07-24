from decimal import Decimal

import pytest

from aipro.intelligence.domain_regime import (
    Domain,
    Regime,
    RegimeFeatures,
    StrategyCandidate,
)
from aipro.intelligence.paper_strategy_validation import (
    ForecastEvidence,
    PaperMarketSnapshot,
    public_validation_evidence,
    validate_paper_strategy,
)


FEATURE_FP = "a" * 64


def features(domain=Domain.CRYPTO, **overrides):
    values = dict(
        domain=domain,
        trend_return=0.05,
        realized_volatility=0.20,
        volatility_zscore=0.1,
        drawdown=-0.02,
        breadth=0.4,
        momentum=0.5,
        liquidity_stress=0.1,
    )
    values.update(overrides)
    return RegimeFeatures(**values)


def candidate(domain=Domain.CRYPTO, ev=0.03, uncertainty=0.1):
    return StrategyCandidate(
        name="trend_v1",
        supported_domains=frozenset({domain}),
        supported_regimes=frozenset({Regime.TREND_UP}),
        expected_value=ev,
        uncertainty=uncertainty,
    )


def forecast(**overrides):
    values = dict(
        win_probability=0.65,
        expected_gain_pct=0.04,
        expected_loss_pct=0.02,
        uncertainty=0.1,
        model_id="crypto_model_v1",
        feature_fingerprint=FEATURE_FP,
    )
    values.update(overrides)
    return ForecastEvidence(**values)


def market(symbol="KRW-BTC", **overrides):
    values = dict(
        symbol=symbol,
        equity=Decimal("1000000"),
        unit_price=Decimal("100000000"),
        stop_distance_pct=0.02,
        forecast_volatility_pct=0.02,
        fee_rate=Decimal("0.0005"),
        spread_bps=Decimal("2"),
        base_slippage_bps=Decimal("1"),
        latency_ms=100,
        volatility_bps_per_sqrt_second=Decimal("2"),
        visible_depth_notional=Decimal("1000000000"),
    )
    values.update(overrides)
    return PaperMarketSnapshot(**values)


def test_positive_crypto_path_produces_paper_evidence():
    result = validate_paper_strategy(
        domain=Domain.CRYPTO,
        features=features(),
        candidates=[candidate()],
        forecast=forecast(),
        market=market(),
    )
    assert result.eligible is True
    assert result.reason == "paper_validation_eligible"
    assert result.paper_only is True
    assert result.sizing is not None and result.sizing.eligible
    assert result.execution is not None and result.execution.status == "FILLED"
    assert len(result.fingerprint) == 64
    assert public_validation_evidence(result)["paper_only"] is True


def test_us_stock_domain_is_mapped_without_cross_domain_state():
    result = validate_paper_strategy(
        domain=Domain.US_STOCK,
        features=features(domain=Domain.US_STOCK),
        candidates=[candidate(domain=Domain.US_STOCK)],
        forecast=forecast(model_id="us_model_v1"),
        market=market(symbol="SPY", unit_price=Decimal("500")),
    )
    assert result.domain == "us_stocks"
    assert result.sizing is not None and result.sizing.domain == "us_stocks"
    assert result.execution is not None


def test_strategy_abstention_stops_before_sizing_and_execution():
    result = validate_paper_strategy(
        domain=Domain.CRYPTO,
        features=features(momentum=0.6, trend_return=0.0),
        candidates=[candidate()],
        forecast=forecast(),
        market=market(),
    )
    assert result.eligible is False
    assert result.reason == "strategy_selection_abstained"
    assert result.sizing is None
    assert result.execution is None


def test_provider_outage_fails_closed():
    result = validate_paper_strategy(
        domain=Domain.CRYPTO,
        features=features(),
        candidates=[candidate()],
        forecast=forecast(),
        market=market(provider_available=False),
    )
    assert result.eligible is False
    assert result.reason == "provider_unavailable"
    assert result.execution is not None and result.execution.status == "REJECTED"


def test_execution_cost_can_eliminate_model_edge():
    result = validate_paper_strategy(
        domain=Domain.CRYPTO,
        features=features(),
        candidates=[candidate()],
        forecast=forecast(
            win_probability=0.51,
            expected_gain_pct=0.010,
            expected_loss_pct=0.009,
        ),
        market=market(
            fee_rate=Decimal("0.002"),
            spread_bps=Decimal("20"),
            base_slippage_bps=Decimal("20"),
        ),
    )
    assert result.eligible is False
    assert result.reason in {"execution_cost_eliminates_edge", "non_positive_risk_adjusted_edge"}


def test_partial_fill_is_not_marked_eligible():
    result = validate_paper_strategy(
        domain=Domain.CRYPTO,
        features=features(),
        candidates=[candidate()],
        forecast=forecast(),
        market=market(visible_depth_notional=Decimal("1000")),
    )
    assert result.eligible is False
    assert result.reason == "partial_fill_only"


def test_invalid_lineage_and_domain_mismatch_fail_closed():
    with pytest.raises(ValueError, match="feature_fingerprint"):
        validate_paper_strategy(
            domain=Domain.CRYPTO,
            features=features(),
            candidates=[candidate()],
            forecast=forecast(feature_fingerprint="bad"),
            market=market(),
        )
    with pytest.raises(ValueError, match="domain mismatch"):
        validate_paper_strategy(
            domain=Domain.CRYPTO,
            features=features(domain=Domain.US_STOCK),
            candidates=[candidate()],
            forecast=forecast(),
            market=market(),
        )


def test_fingerprint_is_deterministic_and_lineage_sensitive():
    kwargs = dict(
        domain=Domain.CRYPTO,
        features=features(),
        candidates=[candidate()],
        forecast=forecast(),
        market=market(),
    )
    first = validate_paper_strategy(**kwargs)
    second = validate_paper_strategy(**kwargs)
    changed = validate_paper_strategy(**{**kwargs, "forecast": forecast(model_id="crypto_model_v2")})
    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint
