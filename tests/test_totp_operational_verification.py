from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from aipro.core.auth_adapters import TotpVerifier
from aipro.core.verify_totp import TotpOperationalStore, verify_totp_operationally


SECRET = "JBSWY3DPEHPK3PXP"


def _code(verifier: TotpVerifier, at_utc: datetime) -> str:
    counter = int(at_utc.timestamp()) // verifier.period_seconds
    return verifier._code_for_counter(counter)


def test_accepts_current_code_and_records_redacted_evidence(tmp_path) -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
    verifier = TotpVerifier(SECRET, window=0)
    store = TotpOperationalStore(tmp_path / "totp.sqlite3")

    evidence = verify_totp_operationally(
        verifier=verifier,
        code=_code(verifier, now),
        enrollment_label="AiPro operator@example.com",
        store=store,
        at_utc=now,
    )

    assert evidence.outcome == "accepted"
    assert evidence.reason == "current_code_verified"
    assert len(evidence.enrollment_hash) == 64
    assert SECRET not in evidence.fingerprint
    assert store.count() == 1


def test_rejects_invalid_code_without_persisting_plaintext(tmp_path) -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
    verifier = TotpVerifier(SECRET, window=0)
    path = tmp_path / "totp.sqlite3"
    store = TotpOperationalStore(path)

    evidence = verify_totp_operationally(
        verifier=verifier,
        code="000000",
        enrollment_label="AiPro operator",
        store=store,
        at_utc=now,
    )

    assert evidence.outcome == "rejected"
    assert evidence.reason == "invalid_code"
    with sqlite3.connect(path) as db:
        serialized = repr(db.execute("SELECT * FROM totp_operational_evidence").fetchall())
    assert "000000" not in serialized
    assert SECRET not in serialized


def test_rejects_reuse_in_same_counter_window(tmp_path) -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
    verifier = TotpVerifier(SECRET, window=0)
    store = TotpOperationalStore(tmp_path / "totp.sqlite3")
    code = _code(verifier, now)

    first = verify_totp_operationally(
        verifier=verifier,
        code=code,
        enrollment_label="AiPro operator",
        store=store,
        at_utc=now,
    )
    second = verify_totp_operationally(
        verifier=verifier,
        code=code,
        enrollment_label="AiPro operator",
        store=store,
        at_utc=now + timedelta(seconds=1),
    )

    assert first.outcome == "accepted"
    assert second.outcome == "rejected"
    assert second.reason == "replay_detected"
    assert store.count() == 2


def test_allows_new_code_in_later_counter_window(tmp_path) -> None:
    now = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
    later = now + timedelta(seconds=30)
    verifier = TotpVerifier(SECRET, window=0)
    store = TotpOperationalStore(tmp_path / "totp.sqlite3")

    first = verify_totp_operationally(
        verifier=verifier,
        code=_code(verifier, now),
        enrollment_label="AiPro operator",
        store=store,
        at_utc=now,
    )
    second = verify_totp_operationally(
        verifier=verifier,
        code=_code(verifier, later),
        enrollment_label="AiPro operator",
        store=store,
        at_utc=later,
    )

    assert first.outcome == second.outcome == "accepted"


def test_evidence_is_append_only(tmp_path) -> None:
    path = tmp_path / "totp.sqlite3"
    store = TotpOperationalStore(path)
    now = datetime(2026, 7, 26, 9, 0, tzinfo=UTC)
    verifier = TotpVerifier(SECRET, window=0)
    verify_totp_operationally(
        verifier=verifier,
        code=_code(verifier, now),
        enrollment_label="AiPro operator",
        store=store,
        at_utc=now,
    )

    with sqlite3.connect(path) as db:
        with pytest.raises(sqlite3.DatabaseError, match="append only"):
            db.execute("UPDATE totp_operational_evidence SET reason = 'changed'")
        with pytest.raises(sqlite3.DatabaseError, match="append only"):
            db.execute("DELETE FROM totp_operational_evidence")


def test_requires_timezone_aware_timestamp(tmp_path) -> None:
    verifier = TotpVerifier(SECRET)
    store = TotpOperationalStore(tmp_path / "totp.sqlite3")
    with pytest.raises(ValueError, match="timezone-aware"):
        verify_totp_operationally(
            verifier=verifier,
            code="123456",
            enrollment_label="AiPro operator",
            store=store,
            at_utc=datetime(2026, 7, 26, 9, 0),
        )
