"""Fail-closed PAPER champion/challenger monitoring.

This module converts immutable evaluation snapshots into governance recommendations.
It never mutates the champion registry, serves a model, contacts a broker, or
creates LIVE/order authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math

from aipro.intelligence.classical_ml import ModelDomain


class Recommendation(str, Enum):
    HOLD = "hold"
    REVIEW_REPLACEMENT = "review_replacement"
    REVIEW_ROLLBACK = "review_rollback"
    DEACTIVATE = "deactivate"
    ABSTAIN = "abstain"


@dataclass(frozen=True)
class MonitoringPolicy:
    max_drift_score: float = 0.20
    max_brier_score: float = 0.25
    min_expected_value_bps: float = 0.0
    max_drawdown_pct: float = 10.0
    min_challenger_score_margin: float = 0.01
    min_challenger_ev_margin_bps: float = 1.0
    min_observations: int = 300

    def __post_init__(self) -> None:
        if not 0.0 <= self.max_drift_score <= 1.0:
            raise ValueError("max_drift_score must be in [0, 1]")
        if not 0.0 <= self.max_brier_score <= 1.0:
            raise ValueError("max_brier_score must be in [0, 1]")
        if self.max_drawdown_pct < 0.0:
            raise ValueError("max_drawdown_pct must be non-negative")
        if self.min_challenger_score_margin < 0.0:
            raise ValueError("min_challenger_score_margin must be non-negative")
        if self.min_challenger_ev_margin_bps < 0.0:
            raise ValueError("min_challenger_ev_margin_bps must be non-negative")
        if self.min_observations <= 0:
            raise ValueError("min_observations must be positive")


@dataclass(frozen=True)
class ModelHealthSnapshot:
    domain: ModelDomain
    candidate_name: str
    candidate_fingerprint: str
    evaluation_fingerprint: str
    score: float
    drift_score: float
    brier_score: float
    expected_value_bps: float
    drawdown_pct: float
    observation_count: int

    def __post_init__(self) -> None:
        if not self.candidate_name.strip():
            raise ValueError("candidate_name is required")
        for name in ("candidate_fingerprint", "evaluation_fingerprint"):
            value = getattr(self, name)
            if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
                raise ValueError(f"{name} must be a lowercase SHA-256 hex digest")
        for name in ("score", "drift_score", "brier_score", "expected_value_bps", "drawdown_pct"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not 0.0 <= self.drift_score <= 1.0:
            raise ValueError("drift_score must be in [0, 1]")
        if not 0.0 <= self.brier_score <= 1.0:
            raise ValueError("brier_score must be in [0, 1]")
        if self.drawdown_pct < 0.0 or self.observation_count < 0:
            raise ValueError("drawdown_pct and observation_count must be non-negative")


@dataclass(frozen=True)
class MonitoringDecision:
    domain: ModelDomain
    recommendation: Recommendation
    champion_name: str
    challenger_name: str | None
    reasons: tuple[str, ...]
    fingerprint: str
    paper_only: bool = True


def assess_challenger(
    champion: ModelHealthSnapshot,
    challenger: ModelHealthSnapshot | None,
    policy: MonitoringPolicy | None = None,
) -> MonitoringDecision:
    """Return a deterministic recommendation without performing any promotion."""

    policy = policy or MonitoringPolicy()
    if challenger is not None and challenger.domain is not champion.domain:
        raise ValueError("champion and challenger domains cannot be mixed")
    if challenger is not None and challenger.candidate_fingerprint == champion.candidate_fingerprint:
        raise ValueError("challenger must differ from champion")

    reasons: list[str] = []
    critical: list[str] = []
    degraded: list[str] = []

    if champion.observation_count < policy.min_observations:
        reasons.append("insufficient_champion_observations")
    if champion.drift_score > policy.max_drift_score:
        degraded.append("champion_drift_exceeded")
    if champion.brier_score > policy.max_brier_score:
        degraded.append("champion_calibration_failed")
    if champion.expected_value_bps <= policy.min_expected_value_bps:
        critical.append("champion_non_positive_expected_value")
    if champion.drawdown_pct > policy.max_drawdown_pct:
        critical.append("champion_drawdown_exceeded")

    reasons.extend(degraded)
    reasons.extend(critical)

    if critical:
        recommendation = Recommendation.DEACTIVATE
    elif reasons and challenger is None:
        recommendation = Recommendation.REVIEW_ROLLBACK if degraded else Recommendation.ABSTAIN
    elif challenger is None:
        recommendation = Recommendation.HOLD
    elif challenger.observation_count < policy.min_observations:
        reasons.append("insufficient_challenger_observations")
        recommendation = Recommendation.REVIEW_ROLLBACK if degraded else Recommendation.HOLD
    elif (
        challenger.drift_score > policy.max_drift_score
        or challenger.brier_score > policy.max_brier_score
        or challenger.expected_value_bps <= policy.min_expected_value_bps
        or challenger.drawdown_pct > policy.max_drawdown_pct
    ):
        reasons.append("challenger_health_gate_failed")
        recommendation = Recommendation.REVIEW_ROLLBACK if degraded else Recommendation.HOLD
    else:
        score_margin = challenger.score - champion.score
        ev_margin = challenger.expected_value_bps - champion.expected_value_bps
        if score_margin >= policy.min_challenger_score_margin and ev_margin >= policy.min_challenger_ev_margin_bps:
            reasons.append("challenger_decisively_better")
            recommendation = Recommendation.REVIEW_REPLACEMENT
        elif degraded:
            reasons.append("no_decisive_healthy_challenger")
            recommendation = Recommendation.REVIEW_ROLLBACK
        else:
            reasons.append("challenger_margin_insufficient")
            recommendation = Recommendation.HOLD

    payload = {
        "domain": champion.domain.value,
        "recommendation": recommendation.value,
        "champion": _snapshot_payload(champion),
        "challenger": _snapshot_payload(challenger) if challenger else None,
        "reasons": reasons,
        "policy": policy.__dict__,
        "paper_only": True,
    }
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return MonitoringDecision(
        domain=champion.domain,
        recommendation=recommendation,
        champion_name=champion.candidate_name,
        challenger_name=challenger.candidate_name if challenger else None,
        reasons=tuple(reasons),
        fingerprint=fingerprint,
    )


def _snapshot_payload(snapshot: ModelHealthSnapshot) -> dict[str, object]:
    return {
        "domain": snapshot.domain.value,
        "candidate_name": snapshot.candidate_name,
        "candidate_fingerprint": snapshot.candidate_fingerprint,
        "evaluation_fingerprint": snapshot.evaluation_fingerprint,
        "score": snapshot.score,
        "drift_score": snapshot.drift_score,
        "brier_score": snapshot.brier_score,
        "expected_value_bps": snapshot.expected_value_bps,
        "drawdown_pct": snapshot.drawdown_pct,
        "observation_count": snapshot.observation_count,
    }
