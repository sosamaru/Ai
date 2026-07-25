import sqlite3

import pytest

from aipro.intelligence.challenger_monitor import MonitoringDecision, Recommendation
from aipro.intelligence.classical_ml import ModelDomain
from aipro.intelligence.governance_approval import GovernanceApprovalLedger, ReviewOutcome


def _decision(
    recommendation: Recommendation = Recommendation.REVIEW_REPLACEMENT,
    domain: ModelDomain = ModelDomain.CRYPTO,
    fingerprint: str = "a" * 64,
) -> MonitoringDecision:
    return MonitoringDecision(
        domain=domain,
        recommendation=recommendation,
        champion_name="champion",
        challenger_name="challenger",
        reasons=("evidence",),
        fingerprint=fingerprint,
    )


def test_records_immutable_operator_review(tmp_path):
    ledger = GovernanceApprovalLedger(tmp_path / "approval.sqlite3")
    event = ledger.record(
        _decision(), ReviewOutcome.APPROVE, "operator-1", "paper replacement reviewed"
    )

    assert event.outcome is ReviewOutcome.APPROVE
    assert event.paper_only is True
    assert event.grants_execution_authority is False
    assert ledger.latest(ModelDomain.CRYPTO) == event
    assert ledger.verify_chain(ModelDomain.CRYPTO) is True


def test_domain_histories_are_isolated(tmp_path):
    ledger = GovernanceApprovalLedger(tmp_path / "approval.sqlite3")
    ledger.record(_decision(), ReviewOutcome.REJECT, "crypto-reviewer", "not enough evidence")
    ledger.record(
        _decision(
            Recommendation.REVIEW_ROLLBACK,
            ModelDomain.US_STOCK,
            "b" * 64,
        ),
        ReviewOutcome.DEFER,
        "stock-reviewer",
        "await more sessions",
    )

    assert len(ledger.history(ModelDomain.CRYPTO)) == 1
    assert len(ledger.history(ModelDomain.US_STOCK)) == 1
    assert ledger.verify_chain(ModelDomain.CRYPTO)
    assert ledger.verify_chain(ModelDomain.US_STOCK)


def test_duplicate_reviewer_decision_is_rejected(tmp_path):
    ledger = GovernanceApprovalLedger(tmp_path / "approval.sqlite3")
    decision = _decision()
    ledger.record(decision, ReviewOutcome.REJECT, "operator-1", "reject once")

    with pytest.raises(ValueError, match="already recorded"):
        ledger.record(decision, ReviewOutcome.APPROVE, "operator-1", "cannot overwrite")


def test_different_reviewers_may_record_independent_evidence(tmp_path):
    ledger = GovernanceApprovalLedger(tmp_path / "approval.sqlite3")
    decision = _decision()
    ledger.record(decision, ReviewOutcome.APPROVE, "operator-1", "reviewed")
    ledger.record(decision, ReviewOutcome.DEFER, "operator-2", "needs more evidence")

    assert len(ledger.history(ModelDomain.CRYPTO)) == 2
    assert ledger.verify_chain(ModelDomain.CRYPTO)


def test_hold_and_abstain_cannot_be_approved(tmp_path):
    ledger = GovernanceApprovalLedger(tmp_path / "approval.sqlite3")

    for index, recommendation in enumerate((Recommendation.HOLD, Recommendation.ABSTAIN)):
        with pytest.raises(ValueError, match="cannot|no state-changing"):
            ledger.record(
                _decision(recommendation, fingerprint=f"{index + 1}" * 64),
                ReviewOutcome.APPROVE,
                f"operator-{index}",
                "invalid approval",
            )


def test_reviewer_and_reason_are_required(tmp_path):
    ledger = GovernanceApprovalLedger(tmp_path / "approval.sqlite3")

    with pytest.raises(ValueError, match="reviewer_id"):
        ledger.record(_decision(), ReviewOutcome.REJECT, " ", "reason")
    with pytest.raises(ValueError, match="reason"):
        ledger.record(_decision(fingerprint="b" * 64), ReviewOutcome.REJECT, "operator", " ")


def test_update_and_delete_are_blocked(tmp_path):
    path = tmp_path / "approval.sqlite3"
    ledger = GovernanceApprovalLedger(path)
    event = ledger.record(_decision(), ReviewOutcome.REJECT, "operator", "immutable")

    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "UPDATE governance_approval_events SET reason = 'tampered' WHERE event_id = ?",
                (event.event_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute(
                "DELETE FROM governance_approval_events WHERE event_id = ?",
                (event.event_id,),
            )


def test_invalid_monitoring_fingerprint_is_rejected(tmp_path):
    ledger = GovernanceApprovalLedger(tmp_path / "approval.sqlite3")

    with pytest.raises(ValueError, match="SHA-256"):
        ledger.record(_decision(fingerprint="invalid"), ReviewOutcome.REJECT, "operator", "bad")
