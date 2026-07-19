from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from aipro.crypto.live_approval import LiveApprovalStateMachine
from aipro.storage import Storage


class MutableClock:
    def __init__(self, value: datetime) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


def test_approval_requires_exact_sequence_and_survives_restart(tmp_path) -> None:
    storage = Storage(tmp_path / "approval.db")
    clock = MutableClock(datetime(2026, 7, 19, 5, 0, tzinfo=UTC))
    machine = LiveApprovalStateMachine(storage, ttl_seconds=300, clock=clock)

    with pytest.raises(RuntimeError):
        machine.confirm()
    with pytest.raises(RuntimeError):
        machine.consume()

    requested = machine.request()
    assert requested.stage == "REQUESTED"

    restored = LiveApprovalStateMachine(storage, ttl_seconds=300, clock=clock)
    assert restored.status().stage == "REQUESTED"
    assert restored.confirm().stage == "CONFIRMED"

    restored_again = LiveApprovalStateMachine(storage, ttl_seconds=300, clock=clock)
    consumed = restored_again.consume()
    assert consumed.stage == "CONFIRMED"
    assert restored_again.status().stage == "IDLE"


def test_expired_request_fails_closed(tmp_path) -> None:
    storage = Storage(tmp_path / "approval.db")
    clock = MutableClock(datetime(2026, 7, 19, 5, 0, tzinfo=UTC))
    machine = LiveApprovalStateMachine(storage, ttl_seconds=60, clock=clock)
    machine.request()

    clock.value += timedelta(seconds=61)

    assert machine.status().stage == "IDLE"
    with pytest.raises(RuntimeError):
        machine.confirm()


def test_new_request_replaces_previous_sequence(tmp_path) -> None:
    storage = Storage(tmp_path / "approval.db")
    clock = MutableClock(datetime(2026, 7, 19, 5, 0, tzinfo=UTC))
    machine = LiveApprovalStateMachine(storage, ttl_seconds=300, clock=clock)
    first = machine.request()
    clock.value += timedelta(seconds=10)
    second = machine.request()

    assert second.requested_at_utc != first.requested_at_utc
    assert machine.status().stage == "REQUESTED"


def test_naive_clock_is_rejected(tmp_path) -> None:
    storage = Storage(tmp_path / "approval.db")
    machine = LiveApprovalStateMachine(
        storage,
        clock=lambda: datetime(2026, 7, 19, 5, 0),
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        machine.request()
