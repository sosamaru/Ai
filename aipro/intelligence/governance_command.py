"""Explicit PAPER governance command boundary.

This module converts reviewed monitoring evidence into a deterministic command
proposal. It never mutates the champion registry, loads a model, contacts a
broker, or grants PAPER/LIVE execution authority.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json

from aipro.intelligence.challenger_monitor import MonitoringDecision, Recommendation
from aipro.intelligence.classical_ml import ModelDomain
from aipro.intelligence.governance_approval import ApprovalEvent, ReviewOutcome


_CONFIRMATION_PHRASE = "APPLY PAPER GOVERNANCE"
_ALLOWED_RECOMMENDATIONS = {
    Recommendation.REVIEW_REPLACEMENT,
    Recommendation.REVIEW_ROLLBACK,
    Recommendation.DEACTIVATE,
}


@dataclass(frozen=True)
class PaperGovernanceCommand:
    domain: ModelDomain
    action: str
    monitoring_fingerprint: str
    approval_event_id: str
    candidate_name: str | None
    rollback_target_event_id: str | None
    reason: str
    fingerprint: str
    confirmed: bool = False
    paper_only: bool = True
    requires_explicit_apply: bool = True
    grants_execution_authority: bool = False


def build_paper_governance_command(
    decision: MonitoringDecision,
    approval: ApprovalEvent,
    *,
    rollback_target_event_id: str | None = None,
) -> PaperGovernanceCommand:
    """Build a fail-closed command proposal from matching approved evidence."""

    if not decision.paper_only or not approval.paper_only:
        raise ValueError("only PAPER governance evidence is accepted")
    if approval.grants_execution_authority:
        raise ValueError("approval evidence must not grant execution authority")
    if approval.outcome is not ReviewOutcome.APPROVE:
        raise ValueError("an approved operator review is required")
    if approval.domain is not decision.domain:
        raise ValueError("approval and monitoring domains must match")
    if approval.monitoring_fingerprint != decision.fingerprint:
        raise ValueError("approval does not reference this monitoring decision")
    if approval.recommendation is not decision.recommendation:
        raise ValueError("approval recommendation does not match monitoring evidence")
    if decision.recommendation not in _ALLOWED_RECOMMENDATIONS:
        raise ValueError("monitoring recommendation has no registry-changing command")

    candidate_name: str | None = None
    target: str | None = None
    if decision.recommendation is Recommendation.REVIEW_REPLACEMENT:
        candidate_name = (decision.challenger_name or "").strip()
        if not candidate_name:
            raise ValueError("replacement command requires a challenger candidate")
        action = "REPLACE"
    elif decision.recommendation is Recommendation.REVIEW_ROLLBACK:
        target = (rollback_target_event_id or "").strip()
        if not target:
            raise ValueError("rollback command requires an explicit target event ID")
        action = "ROLLBACK"
    else:
        action = "DEACTIVATE"

    payload = {
        "domain": decision.domain.value,
        "action": action,
        "monitoring_fingerprint": decision.fingerprint,
        "approval_event_id": approval.event_id,
        "candidate_name": candidate_name,
        "rollback_target_event_id": target,
        "reason": approval.reason,
        "confirmed": False,
        "paper_only": True,
        "requires_explicit_apply": True,
        "grants_execution_authority": False,
    }
    fingerprint = _fingerprint(payload)
    return PaperGovernanceCommand(
        domain=decision.domain,
        action=action,
        monitoring_fingerprint=decision.fingerprint,
        approval_event_id=approval.event_id,
        candidate_name=candidate_name,
        rollback_target_event_id=target,
        reason=approval.reason,
        fingerprint=fingerprint,
    )


def confirm_paper_governance_command(
    command: PaperGovernanceCommand,
    confirmation_phrase: str,
) -> PaperGovernanceCommand:
    """Confirm a proposal without applying it to any registry or broker."""

    if not command.paper_only or command.grants_execution_authority:
        raise ValueError("invalid governance command authority markers")
    if command.confirmed:
        raise ValueError("governance command is already confirmed")
    if confirmation_phrase != _CONFIRMATION_PHRASE:
        raise ValueError("explicit PAPER governance confirmation phrase is required")

    payload = {
        "domain": command.domain.value,
        "action": command.action,
        "monitoring_fingerprint": command.monitoring_fingerprint,
        "approval_event_id": command.approval_event_id,
        "candidate_name": command.candidate_name,
        "rollback_target_event_id": command.rollback_target_event_id,
        "reason": command.reason,
        "proposal_fingerprint": command.fingerprint,
        "confirmed": True,
        "paper_only": True,
        "requires_explicit_apply": True,
        "grants_execution_authority": False,
    }
    return replace(command, confirmed=True, fingerprint=_fingerprint(payload))


def _fingerprint(payload: dict[str, object]) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
