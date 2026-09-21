"""Versioned eight-regime detection and bounded, domain-isolated ensembles."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
from statistics import fmean

from aipro.core.evidence import digest, domain, finite, fingerprint, instant, integer
from aipro.intelligence.domain_regime import RegimeFeatures


class AdaptiveRegime(str, Enum):
    STRONG_BULL = "strong_bull"
    WEAK_BULL = "weak_bull"
    SIDEWAYS = "sideways"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    WEAK_BEAR = "weak_bear"
    STRONG_BEAR = "strong_bear"
    CRASH = "crash_abnormal"


def adaptive_regime(features: RegimeFeatures) -> AdaptiveRegime:
    features.validate()
    # Liquidity collapse is independently sufficient for emergency protection;
    # ordinary market classifications always combine trend/momentum/volatility.
    if features.liquidity_stress >= .8 or features.drawdown <= -.15 and features.momentum < 0:
        return AdaptiveRegime.CRASH
    if features.volatility_zscore >= 2 and features.realized_volatility > 0:
        return AdaptiveRegime.HIGH_VOLATILITY
    if features.trend_return >= .04 and features.momentum >= .5 and features.breadth >= 0:
        return AdaptiveRegime.STRONG_BULL
    if features.trend_return <= -.04 and features.momentum <= -.5 and features.breadth <= 0:
        return AdaptiveRegime.STRONG_BEAR
    if features.volatility_zscore <= -1 and abs(features.trend_return) < .02:
        return AdaptiveRegime.LOW_VOLATILITY
    if features.trend_return > .005 and features.momentum > 0:
        return AdaptiveRegime.WEAK_BULL
    if features.trend_return < -.005 and features.momentum < 0:
        return AdaptiveRegime.WEAK_BEAR
    return AdaptiveRegime.SIDEWAYS


@dataclass(frozen=True)
class Prediction:
    model_id: str
    domain: str
    symbol: str
    at: str
    horizon_seconds: int
    feature_fingerprint: str
    predicted_return: float
    win_probability: float
    expected_gain: float
    expected_loss: float
    expected_volatility: float
    confidence: float
    uncertainty: float
    tail_loss: float
    fees: float
    slippage: float
    supported_regimes: tuple[str, ...]

    def __post_init__(self):
        domain(self.domain)
        instant(self.at)
        digest(self.feature_fingerprint)
        integer(self.horizon_seconds, "prediction horizon", 1, 86400 * 30)
        if not self.model_id or not self.symbol or not self.supported_regimes:
            raise ValueError("identified model, symbol and regime support required")
        for value in self.supported_regimes:
            AdaptiveRegime(value)
        finite(self.predicted_return, "return", -1, 10)
        for name in ("win_probability", "expected_gain", "expected_loss", "expected_volatility", "confidence", "uncertainty", "tail_loss", "fees", "slippage"):
            finite(getattr(self, name), name, 0, 1)
        if self.expected_loss <= 0 or self.expected_volatility <= 0:
            raise ValueError("positive loss and volatility estimates required")
        if abs(self.predicted_return - (self.win_probability * self.expected_gain - (1 - self.win_probability) * self.expected_loss)) > 1e-8:
            raise ValueError("expected return disagrees with declared binary payoff model")


@dataclass(frozen=True)
class EnsemblePolicy:
    min_weight: float = .05
    max_weight: float = .60
    max_weight_step: float = .05
    entry_ev_floor: float = .0005
    max_entry_ev_floor: float = .005
    confidence_floor: float = .55
    max_confidence_floor: float = .85
    risk_penalty: float = .05

    def __post_init__(self):
        for name, value in asdict(self).items():
            finite(value, name, 0, 1)
        if not 0 < self.min_weight < self.max_weight < 1 or not 0 < self.max_weight_step <= .1:
            raise ValueError("model dominance and per-update weight limits required")
        if self.entry_ev_floor > self.max_entry_ev_floor or self.confidence_floor > self.max_confidence_floor:
            raise ValueError("invalid adaptive threshold bounds")


def bounded_weights(scores: dict[str, float], policy=EnsemblePolicy()) -> dict[str, float]:
    if not scores or len(scores) > 20:
        raise ValueError("bounded candidate set required")
    n = len(scores)
    if n * policy.min_weight > 1 or n * policy.max_weight < 1:
        raise ValueError("infeasible ensemble caps; abstain instead of allowing one model dominance")
    for value in scores.values():
        finite(value, "model score")
    # Euclidean projection onto a capped simplex. Deterministic bisection.
    low, high = min(scores.values()) - 1, max(scores.values()) + 1
    for _ in range(80):
        offset = (low + high) / 2
        total = sum(min(policy.max_weight, max(policy.min_weight, value - offset)) for value in scores.values())
        if total > 1:
            low = offset
        else:
            high = offset
    return {name: min(policy.max_weight, max(policy.min_weight, scores[name] - high)) for name in sorted(scores)}


def adapt_weights(weights, net_oos_scores, *, observations: int, policy=EnsemblePolicy()):
    integer(observations, "resolved observations", 0, 1000000)
    if set(weights) != set(net_oos_scores) or abs(sum(weights.values()) - 1) > 1e-8:
        raise ValueError("aligned normalized model weights required")
    for value in weights.values():
        finite(value, "weight", policy.min_weight, policy.max_weight)
    target = bounded_weights(net_oos_scores, policy)
    if observations < 30:
        return dict(weights)
    largest = max(abs(target[k] - weights[k]) for k in weights)
    fraction = min(1, policy.max_weight_step / largest) if largest else 0
    return {k: weights[k] + fraction * (target[k] - weights[k]) for k in sorted(weights)}


def combine(predictions, weights, *, regime: AdaptiveRegime, now, degradation=0.0, policy=EnsemblePolicy()):
    predictions = tuple(predictions)
    finite(degradation, "degradation", 0, 1)
    if len(predictions) < 2:
        return {"allowed": False, "reason": "insufficient_qualified_models"}
    first = predictions[0]
    identity = lambda p: (p.domain, p.symbol, p.at, p.horizon_seconds, p.feature_fingerprint)
    if any(identity(p) != identity(first) for p in predictions) or instant(first.at) != instant(now):
        raise ValueError("ensemble domain, symbol, time, horizon or feature mismatch")
    if len({p.model_id for p in predictions}) != len(predictions) or set(weights) != {p.model_id for p in predictions}:
        raise ValueError("unique aligned models required")
    if regime is AdaptiveRegime.CRASH:
        return {"allowed": False, "reason": "abnormal_market"}
    if any(regime.value not in p.supported_regimes for p in predictions):
        return {"allowed": False, "reason": "unsupported_regime_requires_separate_qualified_ensemble"}
    if abs(sum(weights.values()) - 1) > 1e-8:
        raise ValueError("ensemble weights must sum to one")
    for weight in weights.values():
        finite(weight, "weight", policy.min_weight, policy.max_weight)
    mean = lambda field: sum(weights[p.model_id] * getattr(p, field) for p in predictions)
    expected = mean("predicted_return")
    disagreement = math.sqrt(sum(weights[p.model_id] * (p.predicted_return - expected) ** 2 for p in predictions))
    uncertainty = min(1.0, mean("uncertainty") + disagreement / max(mean("expected_volatility"), 1e-8))
    confidence = min(mean("confidence"), 1 - uncertainty)
    penalty = policy.risk_penalty * max(p.tail_loss for p in predictions) + disagreement
    net_ev = expected - mean("fees") - mean("slippage") - penalty
    ev_floor = policy.entry_ev_floor + degradation * (policy.max_entry_ev_floor - policy.entry_ev_floor)
    confidence_floor = policy.confidence_floor + degradation * (policy.max_confidence_floor - policy.confidence_floor)
    body = {"domain": first.domain, "symbol": first.symbol, "regime": regime.value, "weights": weights,
            "predicted_return": expected, "win_probability": mean("win_probability"),
            "loss_probability": 1 - mean("win_probability"), "expected_volatility": mean("expected_volatility"),
            "confidence": confidence, "uncertainty": uncertainty, "tail_loss": max(p.tail_loss for p in predictions),
            "fees": mean("fees"), "slippage": mean("slippage"), "risk_penalty": penalty,
            "net_ev": net_ev, "entry_threshold": ev_floor, "confidence_threshold": confidence_floor,
            "allowed": net_ev > ev_floor and confidence >= confidence_floor, "paper_only": True}
    return {**body, "fingerprint": fingerprint(body)}
