from decimal import Decimal

import pytest

from aipro.intelligence.execution_simulator import ExecutionRequest, simulate_execution


def request(**overrides):
    data = dict(
        domain="crypto",
        symbol="KRW-BTC",
        side="BUY",
        quantity=Decimal("0.01"),
        reference_price=Decimal("100000000"),
        fee_rate=Decimal("0.0005"),
        spread_bps=Decimal("4"),
        base_slippage_bps=Decimal("3"),
        latency_ms=250,
        volatility_bps_per_sqrt_second=Decimal("8"),
        visible_depth_notional=Decimal("20000000"),
        max_participation_rate=Decimal("0.10"),
        impact_coefficient_bps=Decimal("20"),
    )
    data.update(overrides)
    return ExecutionRequest(**data)


def test_full_fill_is_costed_and_adverse_for_buy():
    result = simulate_execution(request())
    assert result.status == "FILLED"
    assert result.fill_ratio == Decimal("1")
    assert result.execution_price > Decimal("100000000")
    assert result.total_cost > 0
    assert result.effective_cost_bps > 0
    assert len(result.fingerprint) == 64


def test_sell_execution_is_below_reference_price():
    result = simulate_execution(request(side="SELL"))
    assert result.status == "FILLED"
    assert result.execution_price < Decimal("100000000")


def test_partial_fill_respects_depth_and_participation():
    result = simulate_execution(
        request(quantity=Decimal("1"), visible_depth_notional=Decimal("10000000"))
    )
    assert result.status == "PARTIAL"
    assert result.fill_ratio == Decimal("0.01")
    assert result.filled_quantity == Decimal("0.01")
    assert result.unfilled_quantity == Decimal("0.99")


def test_provider_outage_rejects_without_cost():
    result = simulate_execution(request(provider_available=False))
    assert result.status == "REJECTED"
    assert result.execution_price is None
    assert result.total_cost == 0
    assert result.reason == "provider_unavailable"


def test_market_impact_increases_with_participation():
    low = simulate_execution(request(quantity=Decimal("0.001")))
    high = simulate_execution(request(quantity=Decimal("0.01")))
    assert high.effective_cost_bps > low.effective_cost_bps


def test_fingerprint_is_deterministic():
    first = simulate_execution(request())
    second = simulate_execution(request())
    assert first.fingerprint == second.fingerprint


@pytest.mark.parametrize(
    "overrides",
    [
        {"quantity": Decimal("0")},
        {"reference_price": Decimal("-1")},
        {"fee_rate": Decimal("-0.1")},
        {"latency_ms": -1},
        {"max_participation_rate": Decimal("1.1")},
        {"domain": "combined"},
    ],
)
def test_invalid_inputs_fail_closed(overrides):
    with pytest.raises(ValueError):
        simulate_execution(request(**overrides))
