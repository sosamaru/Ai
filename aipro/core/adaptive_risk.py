"""Bounded adaptive proposals beneath immutable core risk limits.

No broker or model reference is available here. PAPER_ONLY means no new entries
in the managed book; a separate shadow book may continue collecting evidence.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from statistics import fmean

from aipro.core.evidence import finite, fingerprint, integer


class RiskMode(str, Enum):
    NORMAL = "NORMAL"
    REDUCED_RISK = "REDUCED_RISK"
    PAPER_ONLY = "PAPER_ONLY"
    HALTED = "HALTED"


@dataclass(frozen=True)
class CoreRiskPolicy:
    max_drawdown: float = .10
    reduced_drawdown: float = .03
    paper_drawdown: float = .06
    max_position: float = .40
    max_exposure: float = .95
    max_correlation: float = .85
    max_correlated_exposure: float = .50
    max_spread_bps: float = 25.0
    max_slippage_bps: float = 30.0
    min_observations: int = 30
    recovery_windows: int = 3
    max_api_failures: int = 3

    def __post_init__(self):
        for name in ("max_drawdown", "reduced_drawdown", "paper_drawdown", "max_position", "max_exposure", "max_correlation", "max_correlated_exposure"):
            finite(getattr(self, name), name, .001, 1)
        if not self.reduced_drawdown < self.paper_drawdown < self.max_drawdown:
            raise ValueError("risk stages must precede the immutable drawdown stop")
        for name in ("max_spread_bps", "max_slippage_bps"):
            finite(getattr(self, name), name, 0, 1000)
        integer(self.min_observations, "min observations", 20, 10000)
        integer(self.recovery_windows, "recovery windows", 2, 30)
        integer(self.max_api_failures, "API failure budget", 1, 20)

    @property
    def fingerprint(self):
        return fingerprint(asdict(self))


@dataclass(frozen=True)
class HealthEvidence:
    observation_id: str
    drawdown: float = 0.0
    observations: int = 0
    net_ev: float | None = None
    feature_drift: float = 0.0
    prediction_drift: float = 0.0
    brier: float | None = None
    ece: float | None = None
    win_rate_drop: float = 0.0
    sharpe_drop: float = 0.0
    stale_data: bool = False
    api_failures: int = 0
    abnormal_market: bool = False

    def __post_init__(self):
        if not self.observation_id:
            raise ValueError("independent observation ID required")
        for name in ("drawdown", "feature_drift", "prediction_drift", "win_rate_drop"):
            finite(getattr(self, name), name, 0, 1)
        for name in ("brier", "ece"):
            if getattr(self, name) is not None:
                finite(getattr(self, name), name, 0, 1)
        if self.net_ev is not None:
            finite(self.net_ev, "net EV")
        finite(self.sharpe_drop, "Sharpe degradation", 0)
        integer(self.observations, "observations", 0, 10000000)
        integer(self.api_failures, "API failures", 0, 10000000)
        if type(self.stale_data) is not bool or type(self.abnormal_market) is not bool:
            raise ValueError("health flags must be boolean")


def update_health(state: dict | None, evidence: HealthEvidence, policy: CoreRiskPolicy) -> dict:
    previous = state or {"mode": RiskMode.NORMAL.value, "healthy_windows": 0, "last_observation": "",
                         "policy_fingerprint": policy.fingerprint, "reasons": ["unvalidated_paper_baseline"]}
    if previous["policy_fingerprint"] != policy.fingerprint:
        raise ValueError("core risk policy changed; explicit migration required")
    mode = RiskMode(previous["mode"])
    if evidence.observation_id == previous["last_observation"]:
        return dict(previous)
    target, reasons = RiskMode.NORMAL, []
    if evidence.abnormal_market or evidence.drawdown >= policy.max_drawdown or evidence.api_failures >= policy.max_api_failures:
        target, reasons = RiskMode.HALTED, ["abnormal_market_or_core_limit"]
    elif (evidence.stale_data or evidence.drawdown >= policy.paper_drawdown
          or max(evidence.feature_drift, evidence.prediction_drift) >= .5
          or evidence.brier is not None and evidence.brier > .35
          or evidence.observations >= policy.min_observations * 2 and evidence.net_ev is not None and evidence.net_ev <= 0):
        target, reasons = RiskMode.PAPER_ONLY, ["data_or_performance_gate"]
    elif (evidence.drawdown >= policy.reduced_drawdown
          or max(evidence.feature_drift, evidence.prediction_drift) >= .2
          or evidence.observations >= policy.min_observations and evidence.net_ev is not None and evidence.net_ev <= 0
          or evidence.brier is not None and evidence.brier > .25
          or evidence.ece is not None and evidence.ece > .10
          or evidence.win_rate_drop > .10 or evidence.sharpe_drop > 1):
        target, reasons = RiskMode.REDUCED_RISK, ["degradation_detected"]
    ranks = {value: index for index, value in enumerate(RiskMode)}
    healthy = 0
    recovery_count = previous.get("last_recovery_count", evidence.observations)
    if mode is RiskMode.HALTED:
        target, reasons = RiskMode.HALTED, ["persistent_manual_resume_latch"]
    elif ranks[target] < ranks[mode]:
        # A fresh price alone does not count as recovery of a degraded model.
        qualified = (evidence.observations >= previous.get("last_recovery_count", 0) + policy.min_observations
                     and evidence.net_ev is not None and evidence.net_ev > 0)
        healthy = ((previous["healthy_windows"] + (1 if qualified else 0))
                   if target is RiskMode.NORMAL else 0)
        if qualified:
            recovery_count = evidence.observations
        if healthy < policy.recovery_windows:
            target, reasons = mode, ["awaiting_independent_recovery_windows"]
        else:
            target, healthy = list(RiskMode)[ranks[mode] - 1], 0
    if evidence.observations < policy.min_observations:
        reasons.append("insufficient_performance_evidence")
    if ranks[target] > ranks[mode]:
        recovery_count = evidence.observations
    return {"mode": target.value, "healthy_windows": healthy, "last_observation": evidence.observation_id,
            "last_recovery_count": recovery_count,
            "policy_fingerprint": policy.fingerprint, "reasons": reasons,
            "size_multiplier": {RiskMode.NORMAL: 1.0, RiskMode.REDUCED_RISK: .25,
                                RiskMode.PAPER_ONLY: 0.0, RiskMode.HALTED: 0.0}[target]}


def entry_budget(*, policy: CoreRiskPolicy, state: dict, equity: float, proposed: float,
                 current_symbol: float, current_exposure: float, spread_bps: float,
                 slippage_bps: float, liquid_notional: float, correlations=(), tail_loss: float = 0.0) -> float:
    if state["policy_fingerprint"] != policy.fingerprint:
        raise ValueError("core policy mismatch")
    for name, value in (("equity", equity), ("proposed", proposed), ("symbol exposure", current_symbol),
                        ("portfolio exposure", current_exposure), ("spread", spread_bps),
                        ("slippage", slippage_bps), ("liquidity", liquid_notional), ("tail loss", tail_loss)):
        finite(value, name, 0)
    mode = RiskMode(state["mode"])
    if mode in {RiskMode.HALTED, RiskMode.PAPER_ONLY} or equity == 0:
        return 0.0
    if spread_bps > policy.max_spread_bps or slippage_bps > policy.max_slippage_bps:
        return 0.0
    correlation_cap = equity * policy.max_exposure
    correlated = current_symbol
    for coefficient, exposure in correlations:
        finite(coefficient, "correlation", -1, 1)
        finite(exposure, "correlated exposure", 0)
        if abs(coefficient) >= policy.max_correlation:
            correlated += exposure
    if correlations:
        correlation_cap = max(0, equity * policy.max_correlated_exposure - correlated)
    multiplier = .25 if mode is RiskMode.REDUCED_RISK else 1.0
    tail_cap = equity * .005 / tail_loss if tail_loss > 0 else proposed
    return max(0.0, min(proposed * multiplier, equity * policy.max_position - current_symbol,
                        equity * policy.max_exposure - current_exposure, correlation_cap,
                        liquid_notional, tail_cap))


def retraining_reasons(*, new_resolved_rows: int, since_last_seconds: float, drift: float,
                       brier_change: float, regime_changed: bool, ev_degraded: bool):
    integer(new_resolved_rows, "new rows", 0, 10000000)
    finite(since_last_seconds, "elapsed seconds", 0)
    finite(drift, "drift", 0, 1)
    finite(brier_change, "Brier change", -1, 1)
    if type(regime_changed) is not bool or type(ev_degraded) is not bool:
        raise ValueError("retraining flags must be boolean")
    if since_last_seconds < 86400 or new_resolved_rows < 100:
        return ()
    return tuple(name for flag, name in ((new_resolved_rows >= 500, "new_data"), (drift >= .2, "feature_drift"),
                 (brier_change >= .05, "calibration_drift"), (regime_changed, "regime_change"),
                 (ev_degraded, "negative_ev")) if flag)
