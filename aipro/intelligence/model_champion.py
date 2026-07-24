"""Fail-closed PAPER model champion selection.

This module ranks already-evaluated model candidates. It does not train models,
load market data, submit orders, or authorize LIVE trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from aipro.intelligence.classical_ml import (
    CandidateEvaluation,
    CandidateStatus,
    ModelDomain,
)


@dataclass(frozen=True)
class ChampionPolicy:
    min_score_margin: float = 0.01
    min_expected_value_margin_bps: float = 1.0
    max_brier_score: float = 0.25
    require_positive_expected_value: bool = True

    def __post_init__(self) -> None:
        if self.min_score_margin < 0.0:
            raise ValueError("min_score_margin must be non-negative")
        if self.min_expected_value_margin_bps < 0.0:
            raise ValueError("min_expected_value_margin_bps must be non-negative")
        if not 0.0 <= self.max_brier_score <= 1.0:
            raise ValueError("max_brier_score must be in [0, 1]")


@dataclass(frozen=True)
class ChampionDecision:
    domain: ModelDomain
    champion: CandidateEvaluation | None
    challenger: CandidateEvaluation | None
    approved: bool
    reasons: tuple[str, ...]
    fingerprint: str
    paper_only: bool = True


def select_champion(
    evaluations: Iterable[CandidateEvaluation],
    domain: ModelDomain,
    policy: ChampionPolicy | None = None,
) -> ChampionDecision:
    """Select one PAPER champion only when evidence is decisive.

    Domain mixing, duplicate candidate names, rejected candidates, weak
    calibration, non-positive EV, and indecisive score/EV margins all fail
    closed. A single eligible candidate may be approved because no challenger
    claim is being made; its original evaluation gates must already have passed.
    """

    policy = policy or ChampionPolicy()
    items = tuple(evaluations)
    reasons: list[str] = []

    if any(item.spec.domain is not domain for item in items):
        raise ValueError("candidate domains cannot be mixed")

    names = [item.spec.name for item in items]
    if len(names) != len(set(names)):
        raise ValueError("candidate names must be unique")

    eligible = [
        item
        for item in items
        if item.status is CandidateStatus.ACCEPTED
        and item.mean_brier_score <= policy.max_brier_score
        and (
            not policy.require_positive_expected_value
            or item.mean_expected_value_bps > 0.0
        )
    ]
    eligible.sort(key=lambda item: (-item.score, item.spec.name))

    champion = eligible[0] if eligible else None
    challenger = eligible[1] if len(eligible) > 1 else None

    if champion is None:
        reasons.append("no_eligible_candidate")
    elif challenger is not None:
        score_margin = champion.score - challenger.score
        ev_margin = (
            champion.mean_expected_value_bps
            - challenger.mean_expected_value_bps
        )
        if score_margin < policy.min_score_margin:
            reasons.append("insufficient_score_margin")
        if ev_margin < policy.min_expected_value_margin_bps:
            reasons.append("insufficient_expected_value_margin")

    approved = champion is not None and not reasons
    payload = {
        "domain": domain.value,
        "champion_fingerprint": champion.fingerprint if champion else None,
        "challenger_fingerprint": challenger.fingerprint if challenger else None,
        "approved": approved,
        "reasons": reasons,
        "policy": {
            "min_score_margin": policy.min_score_margin,
            "min_expected_value_margin_bps": policy.min_expected_value_margin_bps,
            "max_brier_score": policy.max_brier_score,
            "require_positive_expected_value": policy.require_positive_expected_value,
        },
        "paper_only": True,
    }
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    return ChampionDecision(
        domain=domain,
        champion=champion,
        challenger=challenger,
        approved=approved,
        reasons=tuple(reasons),
        fingerprint=fingerprint,
    )
