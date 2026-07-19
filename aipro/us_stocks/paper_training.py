from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class PaperTrainingPolicy:
    minimum_calendar_days: int = 30
    minimum_completed_sessions: int = 20
    minimum_orders: int = 50
    maximum_drawdown_pct: float = 8.0
    maximum_daily_loss_pct: float = 3.0
    require_positive_expectancy: bool = True

    def __post_init__(self) -> None:
        if self.minimum_calendar_days < 30:
            raise ValueError("paper training must run for at least 30 calendar days")
        if self.minimum_completed_sessions < 1 or self.minimum_orders < 1:
            raise ValueError("session and order minimums must be positive")
        if not 0 < self.maximum_drawdown_pct <= 100:
            raise ValueError("invalid maximum drawdown")
        if not 0 < self.maximum_daily_loss_pct <= 100:
            raise ValueError("invalid maximum daily loss")


@dataclass(frozen=True, slots=True)
class PaperTrainingEvidence:
    started_at_utc: str
    evaluated_at_utc: str
    completed_sessions: int
    completed_orders: int
    net_return_pct: float
    maximum_drawdown_pct: float
    worst_daily_return_pct: float
    expectancy_per_trade_pct: float
    stale_data_events: int
    duplicate_order_events: int
    unreconciled_order_events: int

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class PaperTrainingDecision:
    passed: bool
    reasons: tuple[str, ...]
    evidence_fingerprint: str


def evaluate_paper_training(
    evidence: PaperTrainingEvidence,
    policy: PaperTrainingPolicy | None = None,
) -> PaperTrainingDecision:
    active_policy = policy or PaperTrainingPolicy()
    started = datetime.fromisoformat(evidence.started_at_utc).astimezone(UTC)
    evaluated = datetime.fromisoformat(evidence.evaluated_at_utc).astimezone(UTC)
    if evaluated < started:
        raise ValueError("evaluated_at_utc must not precede started_at_utc")

    reasons: list[str] = []
    if evaluated - started < timedelta(days=active_policy.minimum_calendar_days):
        reasons.append("MINIMUM_30_DAY_WINDOW_NOT_MET")
    if evidence.completed_sessions < active_policy.minimum_completed_sessions:
        reasons.append("INSUFFICIENT_COMPLETED_SESSIONS")
    if evidence.completed_orders < active_policy.minimum_orders:
        reasons.append("INSUFFICIENT_COMPLETED_ORDERS")
    if evidence.maximum_drawdown_pct > active_policy.maximum_drawdown_pct:
        reasons.append("MAXIMUM_DRAWDOWN_EXCEEDED")
    if evidence.worst_daily_return_pct < -active_policy.maximum_daily_loss_pct:
        reasons.append("MAXIMUM_DAILY_LOSS_EXCEEDED")
    if active_policy.require_positive_expectancy and evidence.expectancy_per_trade_pct <= 0:
        reasons.append("NON_POSITIVE_EXPECTANCY")
    if evidence.stale_data_events:
        reasons.append("STALE_DATA_EVENTS_PRESENT")
    if evidence.duplicate_order_events:
        reasons.append("DUPLICATE_ORDER_EVENTS_PRESENT")
    if evidence.unreconciled_order_events:
        reasons.append("UNRECONCILED_ORDER_EVENTS_PRESENT")

    return PaperTrainingDecision(
        passed=not reasons,
        reasons=tuple(reasons),
        evidence_fingerprint=evidence.fingerprint,
    )


__all__ = [
    "PaperTrainingDecision",
    "PaperTrainingEvidence",
    "PaperTrainingPolicy",
    "evaluate_paper_training",
]
