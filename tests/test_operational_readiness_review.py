from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime

import pytest

from aipro.core.operational_readiness_review import (
    OperationalReadinessReviewStore,
    OperatorAttestationStore,
    build_operational_readiness_review,
    create_attestation,
)


def _seed_sources(tmp_path) -> tuple[str, str, str, str]:
    smtp = str(tmp_path / "smtp.sqlite3")
    with sqlite3.connect(smtp) as db:
        db.execute("CREATE TABLE smtp_verification_evidence(id INTEGER PRIMARY KEY, delivered INTEGER, fingerprint TEXT)")
        db.execute("INSERT INTO smtp_verification_evidence(delivered,fingerprint) VALUES(1,'smtp-fp')")

    totp = str(tmp_path / "totp.sqlite3")
    with sqlite3.connect(totp) as db:
        db.execute("CREATE TABLE totp_operational_evidence(id INTEGER PRIMARY KEY, outcome TEXT, fingerprint TEXT)")
        db.execute("INSERT INTO totp_operational_evidence(outcome,fingerprint) VALUES('accepted','totp-fp')")

    paper = str(tmp_path / "paper.sqlite3")
    with sqlite3.connect(paper) as db:
        db.execute("CREATE TABLE paper_readiness_reports(id INTEGER PRIMARY KEY, payload_json TEXT, fingerprint TEXT)")
        db.execute(
            "INSERT INTO paper_readiness_reports(payload_json,fingerprint) VALUES(?,?)",
            (json.dumps({"qualifying": True}), "paper-fp"),
        )

    attestations = str(tmp_path / "attest.sqlite3")
    store = OperatorAttestationStore(attestations)
    now = datetime(2026, 7, 26, tzinfo=UTC)
    for kind in (
        "mailbox_arrival_confirmed",
        "totp_recovery_stored_offline",
        "upbit_preflight_supervised",
    ):
        store.append(
            create_attestation(
                kind=kind,
                operator_label="owner",
                evidence_note=f"manual evidence for {kind}",
                created_at_utc=now,
            )
        )
    return smtp, totp, paper, attestations


def test_review_is_ready_only_when_every_source_passes(tmp_path) -> None:
    smtp, totp, paper, attestations = _seed_sources(tmp_path)
    review_db = tmp_path / "review.sqlite3"
    review = build_operational_readiness_review(
        smtp_db=smtp,
        totp_db=totp,
        paper_report_db=paper,
        attestation_db=attestations,
        review_store=OperationalReadinessReviewStore(review_db),
        evaluated_at_utc=datetime(2026, 7, 26, 1, tzinfo=UTC),
    )
    assert review.status == "READY_FOR_INDEPENDENT_REVIEW"
    assert review.blockers == ()
    assert set(review.source_fingerprints) >= {"smtp-fp", "totp-fp", "paper-fp"}


def test_review_fails_closed_when_evidence_is_missing(tmp_path) -> None:
    attestation_db = tmp_path / "attest.sqlite3"
    OperatorAttestationStore(attestation_db)
    review = build_operational_readiness_review(
        smtp_db=tmp_path / "missing-smtp.sqlite3",
        totp_db=tmp_path / "missing-totp.sqlite3",
        paper_report_db=tmp_path / "missing-paper.sqlite3",
        attestation_db=attestation_db,
        review_store=OperationalReadinessReviewStore(tmp_path / "review.sqlite3"),
        evaluated_at_utc=datetime(2026, 7, 26, tzinfo=UTC),
    )
    assert review.status == "NOT_READY"
    assert "SMTP_DELIVERY_EVIDENCE_MISSING" in review.blockers
    assert "ALPACA_30_DAY_QUALIFYING_EVIDENCE_MISSING" in review.blockers


def test_attestations_are_append_only_and_validate_kind(tmp_path) -> None:
    path = tmp_path / "attest.sqlite3"
    store = OperatorAttestationStore(path)
    with pytest.raises(ValueError):
        create_attestation(
            kind="enable_live",
            operator_label="owner",
            evidence_note="unsafe",
            created_at_utc=datetime.now(UTC),
        )
    attestation = create_attestation(
        kind="mailbox_arrival_confirmed",
        operator_label="owner",
        evidence_note="message observed in mailbox",
        created_at_utc=datetime.now(UTC),
    )
    store.append(attestation)
    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM operator_attestations")
