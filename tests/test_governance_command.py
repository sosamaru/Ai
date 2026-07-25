import pytest

from aipro.intelligence.challenger_monitor import MonitoringDecision, Recommendation
from aipro.intelligence.classical_ml import ModelDomain
from aipro.intelligence.governance_approval import ApprovalEvent, ReviewOutcome
from aipro.intelligence.governance_command import (
    build_paper_governance_command,
    confirm_paper_governance_command,
)


def _decision(recommendation=Recommendation.REVIEW_REPLACEMENT):
    return MonitoringDecision(
        domain=ModelDomain.CRYPTO,
        recommendation=recommendation,
        champion_name="champion",
        challenger_name="challenger",
        reasons=("review",),
        fingerprint="a" * 64,
    )


def _approval(decision, outcome=ReviewOutcome.APPROVE, **changes):
    values = dict(
        event_id="b" * 64,
        domain=decision.domain,
        monitoring_fingerprint=decision.fingerprint,
        recommendation=decision.recommendation,
        outcome=outcome,
        reviewer_id="operator-1",
        reason="reviewed PAPER governance evidence",
        previous_event_id=None,
        created_at="2026-07-24T00:00:00+00:00",
    )
    values.update(changes)
    return ApprovalEvent(**values)


def test_builds_replacement_proposal_without_execution_authority():
    decision = _decision()
    command = build_paper_governance_command(decision, _approval(decision))

    assert command.action == "REPLACE"
    assert command.candidate_name == "challenger"
    assert command.confirmed is False
    assert command.paper_only is True
    assert command.requires_explicit_apply is True
    assert command.grants_execution_authority is False
    assert len(command.fingerprint) == 64


def test_rollback_requires_explicit_registry_target():
    decision = _decision(Recommendation.REVIEW_ROLLBACK)
    approval = _approval(decision)

    with pytest.raises(ValueError, match="target"):
        build_paper_governance_command(decision, approval)

    command = build_paper_governance_command(
        decision,
        approval,
        rollback_target_event_id="registry-event-1",
    )
    assert command.action == "ROLLBACK"
    assert command.rollback_target_event_id == "registry-event-1"


def test_deactivation_command_has_no_candidate_or_target():
    decision = _decision(Recommendation.DEACTIVATE)
    command = build_paper_governance_command(decision, _approval(decision))

    assert command.action == "DEACTIVATE"
    assert command.candidate_name is None
    assert command.rollback_target_event_id is None


def test_rejected_or_mismatched_approval_fails_closed():
    decision = _decision()

    with pytest.raises(ValueError, match="approved"):
        build_paper_governance_command(
            decision,
            _approval(decision, outcome=ReviewOutcome.REJECT),
        )
    with pytest.raises(ValueError, match="reference"):
        build_paper_governance_command(
            decision,
            _approval(decision, monitoring_fingerprint="c" * 64),
        )
    with pytest.raises(ValueError, match="domains"):
        build_paper_governance_command(
            decision,
            _approval(decision, domain=ModelDomain.US_STOCK),
        )


def test_hold_and_abstain_have_no_registry_command():
    for recommendation in (Recommendation.HOLD, Recommendation.ABSTAIN):
        decision = _decision(recommendation)
        with pytest.raises(ValueError, match="no registry-changing"):
            build_paper_governance_command(decision, _approval(decision))


def test_confirmation_requires_exact_phrase_and_still_does_not_apply():
    decision = _decision()
    proposal = build_paper_governance_command(decision, _approval(decision))

    with pytest.raises(ValueError, match="confirmation phrase"):
        confirm_paper_governance_command(proposal, "yes")

    confirmed = confirm_paper_governance_command(
        proposal,
        "APPLY PAPER GOVERNANCE",
    )
    assert confirmed.confirmed is True
    assert confirmed.requires_explicit_apply is True
    assert confirmed.grants_execution_authority is False
    assert confirmed.fingerprint != proposal.fingerprint

    with pytest.raises(ValueError, match="already confirmed"):
        confirm_paper_governance_command(confirmed, "APPLY PAPER GOVERNANCE")


def test_command_fingerprint_is_deterministic():
    decision = _decision()
    approval = _approval(decision)

    assert build_paper_governance_command(decision, approval).fingerprint == (
        build_paper_governance_command(decision, approval).fingerprint
    )
