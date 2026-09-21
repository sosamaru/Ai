"""Serializable bounded monitoring state, stored with each market's own book."""
from __future__ import annotations

from statistics import fmean

from aipro.core.adaptive_risk import CoreRiskPolicy, HealthEvidence, RiskMode, update_health
from aipro.core.evidence import finite, fingerprint, instant


def observe(state: dict | None, *, observation_id: str, at: str, equity: float,
            initial_equity: float, policy: CoreRiskPolicy, abnormal=False) -> dict:
    finite(equity, "equity", 0)
    finite(initial_equity, "initial equity", .000001)
    instant(at)
    state = dict(state or {})
    if state.get("last_at") and instant(at) < instant(state["last_at"]):
        raise ValueError("monitor observations cannot move backwards")
    peak = max(state.get("peak", initial_equity), equity)
    outcomes = state.get("outcomes", [])
    # Effective performance windows advance only when a closed episode arrives.
    evidence = HealthEvidence(observation_id=observation_id, drawdown=1 - equity / peak,
        observations=state.get("closed_count", 0), net_ev=fmean(outcomes) if outcomes else None,
        feature_drift=state.get("feature_drift", 0), prediction_drift=state.get("prediction_drift", 0),
        brier=state.get("brier"), ece=state.get("ece"), api_failures=state.get("api_failures", 0),
        abnormal_market=abnormal)
    health = update_health(state.get("health"), evidence, policy)
    state.update(peak=peak, equity=equity, last_at=at, health=health)
    return state


def record_outcome(state: dict | None, *, trade_id: str, net_return: float) -> dict:
    finite(net_return, "net episode return", -1)
    state = dict(state or {})
    ids = state.get("recent_outcome_ids", [])
    if trade_id in ids:
        return state
    state["outcomes"] = (state.get("outcomes", []) + [net_return])[-300:]
    state["recent_outcome_ids"] = (ids + [trade_id])[-300:]
    state["closed_count"] = state.get("closed_count", 0) + 1
    return state


def resume_monitor(state: dict, policy: CoreRiskPolicy) -> dict:
    if not state:
        return state
    if state.get("api_failures", 0) or state.get("feature_drift", 0) >= .5:
        raise ValueError("monitor health gate is still active")
    outcomes = state.get("outcomes", [])
    if len(outcomes) >= policy.min_observations and fmean(outcomes) <= 0:
        raise ValueError("nonpositive observed EV; fresh shadow evidence required")
    if 1 - state["equity"] / state["peak"] >= policy.reduced_drawdown:
        raise ValueError("drawdown recovery gate is still active")
    result = dict(state)
    result["health"] = {"mode": RiskMode.REDUCED_RISK.value, "size_multiplier": .25,
                        "healthy_windows": 0, "last_observation": "manual-resume",
                        "policy_fingerprint": policy.fingerprint, "reasons": ["explicit_resume_reduced_risk"]}
    return result
