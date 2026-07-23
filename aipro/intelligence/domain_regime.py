from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from typing import Mapping, Sequence


class Domain(str, Enum):
    CRYPTO = "crypto"
    US_STOCK = "us_stock"


class Regime(str, Enum):
    TREND_UP = "trend_up"
    TREND_DOWN = "trend_down"
    RANGE = "range"
    HIGH_VOLATILITY = "high_volatility"
    LOW_VOLATILITY = "low_volatility"
    RISK_OFF = "risk_off"
    OVERHEATED = "overheated"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class RegimeFeatures:
    domain: Domain
    trend_return: float
    realized_volatility: float
    volatility_zscore: float
    drawdown: float
    breadth: float
    momentum: float
    liquidity_stress: float

    def validate(self) -> None:
        values = (
            self.trend_return,
            self.realized_volatility,
            self.volatility_zscore,
            self.drawdown,
            self.breadth,
            self.momentum,
            self.liquidity_stress,
        )
        if not all(math.isfinite(value) for value in values):
            raise ValueError("regime features must be finite")
        if self.realized_volatility < 0:
            raise ValueError("realized_volatility must be non-negative")
        if not -1.0 <= self.breadth <= 1.0:
            raise ValueError("breadth must be within [-1, 1]")
        if not 0.0 <= self.liquidity_stress <= 1.0:
            raise ValueError("liquidity_stress must be within [0, 1]")
        if self.drawdown > 0:
            raise ValueError("drawdown must be zero or negative")


@dataclass(frozen=True)
class RegimeDecision:
    domain: Domain
    regime: Regime
    confidence: float
    reasons: tuple[str, ...]
    fingerprint: str


@dataclass(frozen=True)
class StrategyCandidate:
    name: str
    supported_domains: frozenset[Domain]
    supported_regimes: frozenset[Regime]
    expected_value: float
    uncertainty: float
    enabled: bool = True

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("strategy name is required")
        if not self.supported_domains:
            raise ValueError("supported_domains cannot be empty")
        if not self.supported_regimes:
            raise ValueError("supported_regimes cannot be empty")
        if not math.isfinite(self.expected_value):
            raise ValueError("expected_value must be finite")
        if not math.isfinite(self.uncertainty) or not 0.0 <= self.uncertainty <= 1.0:
            raise ValueError("uncertainty must be within [0, 1]")


@dataclass(frozen=True)
class StrategySelection:
    domain: Domain
    regime: Regime
    selected_strategy: str | None
    adjusted_score: float
    abstained: bool
    reasons: tuple[str, ...]
    fingerprint: str


def _fingerprint(payload: Mapping[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(raw.encode("utf-8")).hexdigest()


def classify_regime(features: RegimeFeatures) -> RegimeDecision:
    features.validate()
    reasons: list[str] = []

    if features.liquidity_stress >= 0.8 or features.drawdown <= -0.15:
        regime = Regime.RISK_OFF
        confidence = max(features.liquidity_stress, min(1.0, abs(features.drawdown) / 0.25))
        reasons.append("severe drawdown or liquidity stress")
    elif features.volatility_zscore >= 2.0:
        regime = Regime.HIGH_VOLATILITY
        confidence = min(1.0, features.volatility_zscore / 4.0)
        reasons.append("volatility materially above recent baseline")
    elif features.momentum >= 0.8 and features.trend_return >= 0.08:
        regime = Regime.OVERHEATED
        confidence = min(1.0, (features.momentum + min(features.trend_return / 0.2, 1.0)) / 2.0)
        reasons.append("strong momentum and extended positive trend")
    elif features.trend_return >= 0.02 and features.momentum > 0 and features.breadth >= 0:
        regime = Regime.TREND_UP
        confidence = min(1.0, 0.4 + abs(features.trend_return) + 0.2 * features.breadth)
        reasons.append("positive trend, momentum, and breadth")
    elif features.trend_return <= -0.02 and features.momentum < 0:
        regime = Regime.TREND_DOWN
        confidence = min(1.0, 0.4 + abs(features.trend_return) + 0.2 * max(-features.breadth, 0.0))
        reasons.append("negative trend and momentum")
    elif features.volatility_zscore <= -1.0:
        regime = Regime.LOW_VOLATILITY
        confidence = min(1.0, abs(features.volatility_zscore) / 2.0)
        reasons.append("volatility materially below recent baseline")
    elif abs(features.trend_return) < 0.02 and abs(features.momentum) < 0.25:
        regime = Regime.RANGE
        confidence = min(1.0, 0.5 + (0.25 - abs(features.momentum)))
        reasons.append("muted trend and momentum")
    else:
        regime = Regime.UNKNOWN
        confidence = 0.0
        reasons.append("no regime rule met with sufficient evidence")

    payload = {
        "domain": features.domain.value,
        "regime": regime.value,
        "confidence": round(confidence, 12),
        "features": asdict(features),
        "reasons": reasons,
    }
    return RegimeDecision(features.domain, regime, confidence, tuple(reasons), _fingerprint(payload))


def select_strategy(
    *,
    domain: Domain,
    regime_decision: RegimeDecision,
    candidates: Sequence[StrategyCandidate],
    minimum_adjusted_score: float = 0.0,
    minimum_regime_confidence: float = 0.35,
) -> StrategySelection:
    if regime_decision.domain is not domain:
        raise ValueError("regime decision domain mismatch")
    if minimum_adjusted_score < 0:
        raise ValueError("minimum_adjusted_score must be non-negative")
    if not 0.0 <= minimum_regime_confidence <= 1.0:
        raise ValueError("minimum_regime_confidence must be within [0, 1]")

    valid: list[tuple[float, StrategyCandidate]] = []
    for candidate in candidates:
        candidate.validate()
        if not candidate.enabled:
            continue
        if domain not in candidate.supported_domains:
            continue
        if regime_decision.regime not in candidate.supported_regimes:
            continue
        adjusted_score = candidate.expected_value * (1.0 - candidate.uncertainty)
        valid.append((adjusted_score, candidate))

    reasons: list[str] = []
    selected: StrategyCandidate | None = None
    adjusted_score = 0.0

    if regime_decision.confidence < minimum_regime_confidence:
        reasons.append("regime confidence below threshold")
    elif not valid:
        reasons.append("no enabled strategy supports this domain and regime")
    else:
        adjusted_score, selected = max(valid, key=lambda item: (item[0], item[1].name))
        if adjusted_score <= minimum_adjusted_score:
            reasons.append("best risk-adjusted strategy score is not positive enough")
            selected = None
        else:
            reasons.append("selected highest uncertainty-adjusted expected value")

    abstained = selected is None
    payload = {
        "domain": domain.value,
        "regime": regime_decision.regime.value,
        "regime_fingerprint": regime_decision.fingerprint,
        "selected_strategy": selected.name if selected else None,
        "adjusted_score": round(adjusted_score, 12),
        "abstained": abstained,
        "reasons": reasons,
    }
    return StrategySelection(
        domain=domain,
        regime=regime_decision.regime,
        selected_strategy=selected.name if selected else None,
        adjusted_score=adjusted_score,
        abstained=abstained,
        reasons=tuple(reasons),
        fingerprint=_fingerprint(payload),
    )


class DomainStrategyPipeline:
    """PAPER-only domain-isolated regime and strategy selection pipeline."""

    def __init__(self, domain: Domain, candidates: Sequence[StrategyCandidate]) -> None:
        self.domain = domain
        self._candidates = tuple(candidates)
        for candidate in self._candidates:
            candidate.validate()
            if self.domain not in candidate.supported_domains:
                raise ValueError("pipeline cannot contain a foreign-domain strategy")

    def evaluate(self, features: RegimeFeatures) -> tuple[RegimeDecision, StrategySelection]:
        if features.domain is not self.domain:
            raise ValueError("feature domain mismatch")
        regime = classify_regime(features)
        selection = select_strategy(
            domain=self.domain,
            regime_decision=regime,
            candidates=self._candidates,
        )
        return regime, selection
