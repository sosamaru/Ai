from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True, slots=True)
class LiveExecutionInputs:
    explicit_live_guard: bool
    authorization_active: bool
    paper_validation_passed: bool
    training_evidence_passed: bool
    reconciliation_match: bool
    market_data_fresh: bool
    intelligence_fresh: bool
    required_providers_healthy: bool
    risk_limits_passed: bool
    unique_client_order_id: bool
    preflight_accepted: bool
    kill_switch_active: bool
    live_readiness_review_passed: bool
    authorization_expires_at_utc: str


@dataclass(frozen=True, slots=True)
class LiveExecutionDecision:
    allowed: bool
    reasons: tuple[str, ...]


def evaluate_live_execution(inputs: LiveExecutionInputs, *, now_utc: datetime) -> LiveExecutionDecision:
    """Evaluate every mandatory gate without side effects.

    This function does not submit orders. Any false, missing, invalid, or expired
    condition produces a fail-closed decision.
    """

    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")

    checks = (
        (inputs.explicit_live_guard, "LIVE_GUARD_MISSING"),
        (inputs.authorization_active, "TWO_FACTOR_AUTHORIZATION_INACTIVE"),
        (inputs.paper_validation_passed, "PAPER_VALIDATION_NOT_PASSED"),
        (inputs.training_evidence_passed, "TRAINING_EVIDENCE_NOT_PASSED"),
        (inputs.reconciliation_match, "RECONCILIATION_MATCH_MISSING"),
        (inputs.market_data_fresh, "MARKET_DATA_STALE"),
        (inputs.intelligence_fresh, "INTELLIGENCE_STALE"),
        (inputs.required_providers_healthy, "PROVIDER_UNHEALTHY"),
        (inputs.risk_limits_passed, "RISK_LIMIT_FAILED"),
        (inputs.unique_client_order_id, "CLIENT_ORDER_ID_NOT_UNIQUE"),
        (inputs.preflight_accepted, "ORDER_PREFLIGHT_FAILED"),
        (not inputs.kill_switch_active, "KILL_SWITCH_ACTIVE"),
        (inputs.live_readiness_review_passed, "LIVE_READINESS_REVIEW_NOT_PASSED"),
    )
    reasons = [reason for passed, reason in checks if not passed]

    try:
        expires = datetime.fromisoformat(inputs.authorization_expires_at_utc)
        if expires.tzinfo is None:
            raise ValueError
    except (TypeError, ValueError):
        reasons.append("AUTHORIZATION_EXPIRY_INVALID")
    else:
        if now_utc.astimezone(UTC) >= expires.astimezone(UTC):
            reasons.append("AUTHORIZATION_EXPIRED")

    return LiveExecutionDecision(allowed=not reasons, reasons=tuple(reasons))


__all__ = ["LiveExecutionDecision", "LiveExecutionInputs", "evaluate_live_execution"]
