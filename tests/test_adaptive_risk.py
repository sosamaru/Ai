from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from aipro.core.adaptive_risk import CoreRiskPolicy, HealthEvidence, RiskMode, entry_budget, retraining_reasons, update_health
from aipro.core.execution_lifecycle import ExecutionState as S, OrderLifecycle
from aipro.intelligence.adaptive_ensemble import AdaptiveRegime, EnsemblePolicy, Prediction, adapt_weights, adaptive_regime, bounded_weights, combine
from aipro.intelligence.domain_regime import Domain, RegimeFeatures


def test_degradation_reduces_blocks_and_latches_without_auto_resume():
    p = CoreRiskPolicy()
    first = update_health(None, HealthEvidence("one", observations=100, net_ev=.01, feature_drift=.3), p)
    assert first["mode"] == RiskMode.REDUCED_RISK
    second = update_health(first, HealthEvidence("two", observations=100, net_ev=-.001), p)
    assert second["mode"] == RiskMode.PAPER_ONLY
    third = update_health(second, HealthEvidence("three", drawdown=.11), p)
    assert third["mode"] == RiskMode.HALTED
    recovered = update_health(third, HealthEvidence("four", observations=1000, net_ev=.1), p)
    assert recovered["mode"] == RiskMode.HALTED


def test_recovery_requires_new_resolved_observation_windows_not_repeated_prices():
    p = CoreRiskPolicy()
    state = update_health(None, HealthEvidence("drift", observations=100, net_ev=.01, feature_drift=.3), p)
    for index in range(20):
        state = update_health(state, HealthEvidence(str(index), observations=100, net_ev=.01), p)
    assert state["mode"] == RiskMode.REDUCED_RISK
    for count in (130, 160, 190):
        state = update_health(state, HealthEvidence(str(count), observations=count, net_ev=.01), p)
    assert state["mode"] == RiskMode.NORMAL


def test_core_limits_cannot_be_relaxed_by_adaptive_size_field():
    p = CoreRiskPolicy()
    state = update_health(None, HealthEvidence("x"), p)
    state["size_multiplier"] = 100000
    kwargs = dict(policy=p, state=state, equity=1000., proposed=1000., current_symbol=350.,
                  current_exposure=800., spread_bps=10., slippage_bps=5., liquid_notional=1000.)
    assert entry_budget(**kwargs) == 50
    assert entry_budget(**{**kwargs, "spread_bps": 100}) == 0
    assert entry_budget(**{**kwargs, "current_symbol": 0, "correlations": ((.95, 490.),)}) == 10
    with pytest.raises(ValueError, match="policy mismatch"):
        entry_budget(**{**kwargs, "policy": replace(p, max_position=.5)})


@pytest.mark.parametrize("field", ["drawdown", "feature_drift", "brier", "net_ev", "prediction_drift"])
def test_health_rejects_nonfinite_input(field):
    with pytest.raises(ValueError):
        HealthEvidence("bad", **{field: float("nan")})


def test_retraining_needs_data_and_cooldown_and_only_returns_reasons():
    kwargs = dict(new_resolved_rows=500, since_last_seconds=100, drift=.3, brier_change=.1, regime_changed=True, ev_degraded=True)
    assert retraining_reasons(**kwargs) == ()
    assert "feature_drift" in retraining_reasons(**{**kwargs, "since_last_seconds": 90000})


def test_order_partial_timeout_requires_reconciliation_and_cannot_reopen():
    at = datetime(2026, 1, 1, tzinfo=UTC).isoformat()
    order = OrderLifecycle("crypto", "stable-key", 10)
    with pytest.raises(ValueError, match="submitted"):
        order.transition(S.FILLED, cumulative_filled=10, at=at)
    order = order.transition(S.SUBMITTED, cumulative_filled=0, at=at).transition(S.PARTIAL, cumulative_filled=3, at=at)
    order = order.transition(S.UNKNOWN, cumulative_filled=3, at=at)
    with pytest.raises(ValueError, match="reconciliation"):
        order.transition(S.FILLED, cumulative_filled=10, at=at)
    order = order.transition(S.FILLED, cumulative_filled=10, at=at, reconciled=True)
    assert order.transition(S.FILLED, cumulative_filled=10, at=at) == order
    with pytest.raises(ValueError, match="terminal"):
        order.transition(S.CANCELLED, cumulative_filled=10, at=at)


@pytest.mark.parametrize("features,expected", [
    ((.05,.03,0,0,.5,.6,0), AdaptiveRegime.STRONG_BULL),
    ((.01,.03,0,0,.5,.2,0), AdaptiveRegime.WEAK_BULL),
    ((0,.01,0,0,0,0,0), AdaptiveRegime.SIDEWAYS),
    ((.01,.1,3,0,0,.2,0), AdaptiveRegime.HIGH_VOLATILITY),
    ((0,.001,-2,0,0,0,0), AdaptiveRegime.LOW_VOLATILITY),
    ((-.01,.03,0,-.01,-.5,-.2,0), AdaptiveRegime.WEAK_BEAR),
    ((-.05,.03,0,-.05,-.5,-.6,0), AdaptiveRegime.STRONG_BEAR),
    ((-.20,.2,3,-.2,-1,-1,.9), AdaptiveRegime.CRASH),
])
def test_eight_regimes(features, expected):
    assert adaptive_regime(RegimeFeatures(Domain.CRYPTO, *features)) is expected


def test_ensemble_weights_never_dominate_or_jump():
    p = EnsemblePolicy()
    w = bounded_weights({"a": 100., "b": -10., "c": 0.}, p)
    assert sum(w.values()) == pytest.approx(1)
    assert max(w.values()) <= .6 and min(w.values()) >= .05
    changed = adapt_weights(w, {"a": -100., "b": 100., "c": 1.}, observations=100, policy=p)
    assert max(abs(changed[k] - w[k]) for k in w) <= .05 + 1e-9
    with pytest.raises(ValueError, match="infeasible"):
        bounded_weights({"single": 1.})


def prediction(name):
    return Prediction(name, "crypto", "KRW-X", "2026-01-01T00:00:00+00:00", 300, "a" * 64,
                      .65*.04-.35*.02, .65, .04, .02, .02, .9, .1, .05, .001, .001,
                      tuple(x.value for x in AdaptiveRegime))


def test_ensemble_ev_costs_uncertainty_and_domain_boundaries():
    a, b = prediction("a"), prediction("b")
    report = combine([a, b], {"a": .5, "b": .5}, regime=AdaptiveRegime.WEAK_BULL, now=a.at)
    assert report["allowed"] and report["net_ev"] < report["predicted_return"]
    costs = combine([replace(a, fees=.1), replace(b, fees=.1)], {"a": .5, "b": .5}, regime=AdaptiveRegime.WEAK_BULL, now=a.at)
    assert not costs["allowed"]
    with pytest.raises(ValueError, match="mismatch"):
        combine([a, replace(b, domain="us_stock")], {"a": .5, "b": .5}, regime=AdaptiveRegime.WEAK_BULL, now=a.at)
