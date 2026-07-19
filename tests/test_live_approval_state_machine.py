from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from aipro.crypto.live_approval import LiveApprovalError, LiveApprovalStore


FINGERPRINT = "a" * 64


def test_full_sequence_is_persistent_and_restart_safe(tmp_path) -> None:
    database = tmp_path / "approval.sqlite3"
    start = datetime(2026, 7, 19, 5, 0, tzinfo=UTC)
    store = LiveApprovalStore(database)

    requested = store.request(
        operator_id="telegram:123",
        readiness_fingerprint=FINGERPRINT,
        readiness_passed=True,
        halted=False,
        now=start,
    )
    assert requested.state == "REQUESTED"

    restarted = LiveApprovalStore(database)
    confirmed = restarted.confirm(
        approval_id=requested.approval_id,
        operator_id="telegram:123",
        now=start + timedelta(seconds=10),
    )
    assert confirmed.state == "CONFIRMED"

    activated = restarted.activate(
        approval_id=requested.approval_id,
        operator_id="telegram:123",
        readiness_fingerprint=FINGERPRINT,
        readiness_passed=True,
        halted=False,
        live_environment_enabled=True,
        now=start + timedelta(seconds=20),
    )
    assert activated.state == "ACTIVE"
    assert activated.activated_at_utc is not None


def test_request_fails_closed_without_readiness_or_when_halted(tmp_path) -> None:
    store = LiveApprovalStore(tmp_path / "approval.sqlite3")
    now = datetime(2026, 7, 19, 5, 0, tzinfo=UTC)

    with pytest.raises(LiveApprovalError, match="readiness"):
        store.request(
            operator_id="telegram:123",
            readiness_fingerprint=FINGERPRINT,
            readiness_passed=False,
            halted=False,
            now=now,
        )

    with pytest.raises(LiveApprovalError, match="HALTED"):
        store.request(
            operator_id="telegram:123",
            readiness_fingerprint=FINGERPRINT,
            readiness_passed=True,
            halted=True,
            now=now,
        )


def test_operator_mismatch_and_skipped_confirm_are_blocked(tmp_path) -> None:
    store = LiveApprovalStore(tmp_path / "approval.sqlite3")
    now = datetime(2026, 7, 19, 5, 0, tzinfo=UTC)
    requested = store.request(
        operator_id="telegram:123",
        readiness_fingerprint=FINGERPRINT,
        readiness_passed=True,
        halted=False,
        now=now,
    )

    with pytest.raises(LiveApprovalError, match="CONFIRMED"):
        store.activate(
            approval_id=requested.approval_id,
            operator_id="telegram:123",
            readiness_fingerprint=FINGERPRINT,
            readiness_passed=True,
            halted=False,
            live_environment_enabled=True,
            now=now + timedelta(seconds=1),
        )

    with pytest.raises(LiveApprovalError, match="operator mismatch"):
        store.confirm(
            approval_id=requested.approval_id,
            operator_id="telegram:999",
            now=now + timedelta(seconds=2),
        )


def test_expired_sequence_fails_and_current_marks_expired(tmp_path) -> None:
    store = LiveApprovalStore(tmp_path / "approval.sqlite3")
    now = datetime(2026, 7, 19, 5, 0, tzinfo=UTC)
    requested = store.request(
        operator_id="telegram:123",
        readiness_fingerprint=FINGERPRINT,
        readiness_passed=True,
        halted=False,
        ttl_seconds=30,
        now=now,
    )

    with pytest.raises(LiveApprovalError, match="expired"):
        store.confirm(
            approval_id=requested.approval_id,
            operator_id="telegram:123",
            now=now + timedelta(seconds=31),
        )

    current = store.current(now=now + timedelta(seconds=31))
    assert current is not None
    assert current.state == "EXPIRED"


def test_activation_rechecks_all_safety_gates(tmp_path) -> None:
    store = LiveApprovalStore(tmp_path / "approval.sqlite3")
    now = datetime(2026, 7, 19, 5, 0, tzinfo=UTC)
    requested = store.request(
        operator_id="telegram:123",
        readiness_fingerprint=FINGERPRINT,
        readiness_passed=True,
        halted=False,
        now=now,
    )
    store.confirm(
        approval_id=requested.approval_id,
        operator_id="telegram:123",
        now=now + timedelta(seconds=1),
    )

    with pytest.raises(LiveApprovalError, match="changed"):
        store.activate(
            approval_id=requested.approval_id,
            operator_id="telegram:123",
            readiness_fingerprint="b" * 64,
            readiness_passed=True,
            halted=False,
            live_environment_enabled=True,
            now=now + timedelta(seconds=2),
        )

    with pytest.raises(LiveApprovalError, match="HALTED"):
        store.activate(
            approval_id=requested.approval_id,
            operator_id="telegram:123",
            readiness_fingerprint=FINGERPRINT,
            readiness_passed=True,
            halted=True,
            live_environment_enabled=True,
            now=now + timedelta(seconds=3),
        )

    with pytest.raises(LiveApprovalError, match="environment"):
        store.activate(
            approval_id=requested.approval_id,
            operator_id="telegram:123",
            readiness_fingerprint=FINGERPRINT,
            readiness_passed=True,
            halted=False,
            live_environment_enabled=False,
            now=now + timedelta(seconds=4),
        )


def test_revoke_is_persistent_and_audit_is_immutable(tmp_path) -> None:
    database = tmp_path / "approval.sqlite3"
    store = LiveApprovalStore(database)
    now = datetime(2026, 7, 19, 5, 0, tzinfo=UTC)
    requested = store.request(
        operator_id="telegram:123",
        readiness_fingerprint=FINGERPRINT,
        readiness_passed=True,
        halted=False,
        now=now,
    )
    revoked = store.revoke(reason="HALTED latch engaged", now=now + timedelta(seconds=1))
    assert revoked is not None
    assert revoked.approval_id == requested.approval_id
    assert revoked.state == "REVOKED"

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE crypto_live_approval_audit SET reason = 'tampered' WHERE event_id = 1"
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM crypto_live_approval_audit WHERE event_id = 1")


def test_naive_timestamps_and_invalid_ttl_are_rejected(tmp_path) -> None:
    store = LiveApprovalStore(tmp_path / "approval.sqlite3")
    with pytest.raises(ValueError, match="timezone-aware"):
        store.request(
            operator_id="telegram:123",
            readiness_fingerprint=FINGERPRINT,
            readiness_passed=True,
            halted=False,
            now=datetime(2026, 7, 19, 5, 0),
        )
    with pytest.raises(ValueError, match="between 30 and 900"):
        store.request(
            operator_id="telegram:123",
            readiness_fingerprint=FINGERPRINT,
            readiness_passed=True,
            halted=False,
            ttl_seconds=20,
            now=datetime(2026, 7, 19, 5, 0, tzinfo=UTC),
        )
