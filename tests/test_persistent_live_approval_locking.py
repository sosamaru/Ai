from __future__ import annotations

from datetime import UTC, datetime

import pytest

from aipro.crypto.persistent_live_approval import LiveApprovalError, LiveApprovalStore
from aipro.sqlite_utils import connect


FINGERPRINT = "a" * 64


@pytest.mark.parametrize("timeout", [0.0, 31.0, float("nan")])
def test_invalid_lock_timeout_is_rejected(tmp_path, timeout: float) -> None:
    with pytest.raises(ValueError, match="lock_timeout_sec"):
        LiveApprovalStore(tmp_path / "approval.sqlite3", lock_timeout_sec=timeout)


def test_concurrent_transition_fails_closed_when_database_is_busy(tmp_path) -> None:
    database = tmp_path / "approval.sqlite3"
    store = LiveApprovalStore(database, lock_timeout_sec=0.05)
    now = datetime(2026, 7, 30, 10, 0, tzinfo=UTC)

    with connect(database) as blocker:
        blocker.execute("BEGIN IMMEDIATE")
        with pytest.raises(LiveApprovalError, match="busy"):
            store.request(
                operator_id="telegram:123",
                readiness_fingerprint=FINGERPRINT,
                readiness_passed=True,
                halted=False,
                now=now,
            )

    requested = store.request(
        operator_id="telegram:123",
        readiness_fingerprint=FINGERPRINT,
        readiness_passed=True,
        halted=False,
        now=now,
    )
    assert requested.state == "REQUESTED"
