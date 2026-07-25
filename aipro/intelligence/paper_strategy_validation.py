"""Domain-isolated PAPER strategy validation orchestration.

This module joins regime classification, strategy selection, risk-adjusted
position sizing, and deterministic execution-cost simulation. It produces
research evidence only and has no broker or order authority.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal
from hashlib import sha256
import json
from typing import Mapping, Sequence

from aipro.intelligence.domain_regime import (
    Domain,
    DomainStrategyPipeline,
    RegimeDecision,
    RegimeFeatures,
    StrategyCandidate,
    StrategySelection,
)
from aipro.intelligence.execution_simulator import (
    ExecutionRequest,
    ExecutionResult,
    simulate_execution,
)
from aipro.intelligence.risk_adjusted_sizing import (
    PaperSizingDecision,
    PaperSizingPolicy,
    size_paper_position,
)


@dataclass(frozen=True)
class PaperMarketSnapshot:
    symbol: str
    equity: Decimal
    unit_price: Decimal
    stop_distance_pct: float
    forecast_volatility_pct: float
    fee_rate: Decimal
    spread_bps: Decimal
    base_slippage_bps: Decimal
    latency_ms: int
    volatility_bps_per_sqrt_second: Decimal
    visible_depth_notional: Decimal
    provider_available: bool = True


@dataclass(frozen=True)
class ForecastEvidence:
    win_probability: float
    expected_gain_pct: float
    expected_loss_pct: float
    uncertainty: float
    model_id: str
    feature_fingerprint: str


@dataclass(frozen=True)
class PaperStrategyValidation:
    domain: str
    symbol: str
    eligible: bool
    reason: str
    regime: RegimeDecision
    selection: StrategySelection
    sizing: PaperSizingDecision | None
    execution: ExecutionResult | None
    model_id: str
    feature_fingerprint: str
    fingerprint: str
    paper_only: bool = True


def validate_paper_strategy(
    *,
    domain: Domain,
    features: RegimeFeatures,
    candidates: Sequence[StrategyCandidate],
    forecast: ForecastEvidence,
    market: PaperMarketSnapshot,
    sizing_policy: PaperSizingPolicy = PaperSizingPolicy(),
    metadata: Mapping[str, str] | None = None,
) -> PaperStrategyValidation:
    """Evaluate one domain-specific PAPER strategy candidate fail-closed."""
    if features.domain is not domain:
        raise ValueError("feature domain mismatch")
    if not market.symbol.strip() or market.symbol != market.symbol.strip().upper():
        raise ValueError("symbol must be uppercase and normalized")
    if not forecast.model_id.strip():
        raise ValueError("model_id is required")
    if len(forecast.feature_fingerprint) != 64:
        raise ValueError("feature_fingerprint must be a SHA-256 hex digest")
    try:
        int(forecast.feature_fingerprint, 16)
    except ValueError as exc:
        raise ValueError("feature_fingerprint must be hexadecimal") from exc

    pipeline = DomainStrategyPipeline(domain, candidates)
    regime, selection = pipeline.evaluate(features)
    normalized_domain = "crypto" if domain is Domain.CRYPTO else "us_stocks"

    sizing: PaperSizingDecision | None = None
    execution: ExecutionResult | None = None
    eligible = False
    reason = "strategy_selection_abstained"

    if not selection.abstained:
        sizing = size_paper_position(
            domain=normalized_domain,
            symbol=market.symbol,
            equity=market.equity,
            unit_price=market.unit_price,
            stop_distance_pct=market.stop_distance_pct,
            forecast_volatility_pct=market.forecast_volatility_pct,
            uncertainty=forecast.uncertainty,
            win_probability=forecast.win_probability,
            expected_gain_pct=forecast.expected_gain_pct,
            expected_loss_pct=forecast.expected_loss_pct,
            estimated_cost_pct=0.0,
            policy=sizing_policy,
            metadata={
                "model_id": forecast.model_id,
                "feature_fingerprint": forecast.feature_fingerprint,
                "strategy": selection.selected_strategy or "",
                **dict(metadata or {}),
            },
        )
        reason = sizing.reason

        if sizing.eligible and sizing.suggested_quantity > 0:
            execution = simulate_execution(
                ExecutionRequest(
                    domain=normalized_domain,
                    symbol=market.symbol,
                    side="BUY",
                    quantity=sizing.suggested_quantity,
                    reference_price=market.unit_price,
                    fee_rate=market.fee_rate,
                    spread_bps=market.spread_bps,
                    base_slippage_bps=market.base_slippage_bps,
                    latency_ms=market.latency_ms,
                    volatility_bps_per_sqrt_second=market.volatility_bps_per_sqrt_second,
                    visible_depth_notional=market.visible_depth_notional,
                    provider_available=market.provider_available,
                )
            )
            if execution.status == "REJECTED":
                reason = execution.reason
            elif execution.fill_ratio < Decimal("1"):
                reason = "partial_fill_only"
            else:
                round_trip_cost_pct = float(execution.effective_cost_bps * Decimal("2") / Decimal("10000"))
                net_after_execution = sizing.expected_value.net_ev_pct - round_trip_cost_pct
                if net_after_execution <= sizing_policy.min_net_ev_pct:
                    reason = "execution_cost_eliminates_edge"
                else:
                    eligible = True
                    reason = "paper_validation_eligible"

    payload = {
        "domain": normalized_domain,
        "symbol": market.symbol,
        "eligible": eligible,
        "reason": reason,
        "regime_fingerprint": regime.fingerprint,
        "selection_fingerprint": selection.fingerprint,
        "sizing_fingerprint": sizing.fingerprint if sizing else None,
        "execution_fingerprint": execution.fingerprint if execution else None,
        "model_id": forecast.model_id,
        "feature_fingerprint": forecast.feature_fingerprint,
        "paper_only": True,
    }
    fingerprint = sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return PaperStrategyValidation(
        domain=normalized_domain,
        symbol=market.symbol,
        eligible=eligible,
        reason=reason,
        regime=regime,
        selection=selection,
        sizing=sizing,
        execution=execution,
        model_id=forecast.model_id,
        feature_fingerprint=forecast.feature_fingerprint,
        fingerprint=fingerprint,
    )


def public_validation_evidence(result: PaperStrategyValidation) -> Mapping[str, object]:
    """Return serializable immutable research evidence."""
    return asdict(result)
