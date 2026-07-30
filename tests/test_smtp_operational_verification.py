from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

import pytest

from aipro.core.smtp_operational_verification import (
    SmtpVerificationEvidenceStore,
    run_smtp_verification,
)
from aipro.sqlite_utils import connect


class FakeSender:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[dict[str, object]] = []

    def send(self, *, recipient: str, code: str, expires_at_utc: datetime) -> None:
        self.calls.append(
            {
                "recipient": recipient,
                "code": code,
                "expires_at_utc": expires_at_utc,
            }
        )
        if self.fail:
            raise TimeoutError("simulated timeout")


def test_successful_verification_records_redacted_append_only_evidence(tmp_path) -> None:
    db_path = tmp_path / "smtp.sqlite3"
    sender = FakeSender()
    store = SmtpVerificationEvidenceStore(db_path)

    result = run_smtp_verification(
        sender=sender,
        recipient="owner@example.com",
        evidence_store=store,
        now_utc=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        provider="transactional-email",
    )

    assert result.delivered is True
    assert result.reason == "delivery_accepted"
    assert store.count() == 1
    assert len(sender.calls) == 1
    assert str(sender.calls[0]["code"]).isdigit()
    assert len(str(sender.calls[0]["code"])) == 6

    with connect(db_path) as db:
        row = db.execute(
            "SELECT recipient_hash, delivered, provider, reason, fingerprint "
            "FROM smtp_verification_evidence"
        ).fetchone()
        columns = {
            item[1]
            for item in db.execute("PRAGMA table_info(smtp_verification_evidence)").fetchall()
        }

    assert row == (
        result.recipient_hash,
        1,
        "transactional-email",
        "delivery_accepted",
        result.fingerprint,
    )
    assert "recipient" not in columns
    assert "code" not in columns

    with connect(db_path) as db, pytest.raises(sqlite3.DatabaseError):
        db.execute("DELETE FROM smtp_verification_evidence")


def test_failed_delivery_records_exception_type_without_secret_or_message(tmp_path) -> None:
    sender = FakeSender(fail=True)
    store = SmtpVerificationEvidenceStore(tmp_path / "smtp.sqlite3")

    result = run_smtp_verification(
        sender=sender,
        recipient="owner@example.com",
        evidence_store=store,
        now_utc=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
    )

    assert result.delivered is False
    assert result.reason == "delivery_failed:TimeoutError"
    assert "owner@example.com" not in result.reason
    assert store.count() == 1


def test_invalid_recipient_fails_before_delivery_or_evidence(tmp_path) -> None:
    sender = FakeSender()
    store = SmtpVerificationEvidenceStore(tmp_path / "smtp.sqlite3")

    with pytest.raises(ValueError, match="recipient"):
        run_smtp_verification(
            sender=sender,
            recipient="not-an-email",
            evidence_store=store,
            now_utc=datetime(2026, 7, 26, 8, 0, tzinfo=UTC),
        )

    assert sender.calls == []
    assert store.count() == 0


def test_naive_timestamp_is_rejected(tmp_path) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        run_smtp_verification(
            sender=FakeSender(),
            recipient="owner@example.com",
            evidence_store=SmtpVerificationEvidenceStore(tmp_path / "smtp.sqlite3"),
            now_utc=datetime(2026, 7, 26, 8, 0),
        )
