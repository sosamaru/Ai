from decimal import Decimal

import pytest

from aipro.intelligence.risk_adjusted_sizing import (
    PaperSizingPolicy,
    SizingValidationError,
    estimate_expected_value,
    size_paper_position,
)


def test_expected_value_is_cost_aware_and_kelly_is_bounded():
    result = estimate_expected_value(
        win_probability=0.60,
        expected_gain_pct=0.03,
        expected_loss_pct=0.02,
        estimated_cost_pct=0.001,
        max_fractional_kelly=0.25,
    )

    assert result.gross_ev_pct == pytest.approx(0.010)
    assert result.net_ev_pct == pytest.approx(0.009)
    assert 0.0 < result.fractional_kelly <= 0.25


def test_positive_edge_produces_capped_paper_notional():
    decision = size_paper_position(
        domain="crypto",
        symbol="KRW-BTC",
        equity="1000000",
        unit_price="100000000",
        stop_distance_pct=0.02,
        forecast_volatility_pct=0.03,
        uncertainty=0.20,
        win_probability=0.60,
        expected_gain_pct=0.03,
        expected_loss_pct=0.02,
        estimated_cost_pct=0.001,
        policy=PaperSizingPolicy(max_position_pct=0.10),
    )

    assert decision.eligible is True
    assert decision.suggested_notional > Decimal("0")
    assert decision.suggested_notional <= Decimal("100000")
    assert decision.suggested_quantity > Decimal("0")
    assert len(decision.fingerprint) == 64


def test_non_positive_edge_abstains():
    decision = size_paper_position(
        domain="us_stocks",
        symbol="SPY",
        equity="10000",
        unit_price="500",
        stop_distance_pct=0.02,
        forecast_volatility_pct=0.02,
        uncertainty=0.10,
        win_probability=0.40,
        expected_gain_pct=0.01,
        expected_loss_pct=0.02,
        estimated_cost_pct=0.001,
    )

    assert decision.eligible is False
    assert decision.reason == "non_positive_risk_adjusted_edge"
    assert decision.suggested_notional == Decimal("0")
    assert decision.suggested_quantity == Decimal("0")


def test_high_volatility_and_uncertainty_reduce_size():
    base = dict(
        domain="crypto",
        symbol="KRW-ETH",
        equity="1000000",
        unit_price="5000000",
        stop_distance_pct=0.02,
        win_probability=0.60,
        expected_gain_pct=0.03,
        expected_loss_pct=0.02,
    )
    low_risk = size_paper_position(
        **base,
        forecast_volatility_pct=0.01,
        uncertainty=0.0,
    )
    high_risk = size_paper_position(
        **base,
        forecast_volatility_pct=0.05,
        uncertainty=1.0,
    )

    assert high_risk.suggested_notional < low_risk.suggested_notional


def test_domain_isolation_and_malformed_inputs_fail_closed():
    with pytest.raises(SizingValidationError):
        size_paper_position(
            domain="combined",
            symbol="BTC",
            equity="1000",
            unit_price="100",
            stop_distance_pct=0.02,
            forecast_volatility_pct=0.02,
            uncertainty=0.1,
            win_probability=0.6,
            expected_gain_pct=0.03,
            expected_loss_pct=0.02,
        )

    with pytest.raises(SizingValidationError):
        estimate_expected_value(
            win_probability=1.2,
            expected_gain_pct=0.03,
            expected_loss_pct=0.02,
        )


def test_fingerprint_is_deterministic_and_metadata_sensitive():
    kwargs = dict(
        domain="crypto",
        symbol="KRW-BTC",
        equity="1000000",
        unit_price="100000000",
        stop_distance_pct=0.02,
        forecast_volatility_pct=0.03,
        uncertainty=0.20,
        win_probability=0.60,
        expected_gain_pct=0.03,
        expected_loss_pct=0.02,
    )
    first = size_paper_position(**kwargs, metadata={"model": "a", "fold": "1"})
    second = size_paper_position(**kwargs, metadata={"fold": "1", "model": "a"})
    changed = size_paper_position(**kwargs, metadata={"model": "b", "fold": "1"})

    assert first.fingerprint == second.fingerprint
    assert first.fingerprint != changed.fingerprint
