from datetime import UTC, datetime, timedelta

import pytest

from aipro.core.live_authorization import (
    AuthorizationStage,
    LiveAuthorizationManager,
    LiveAuthorizationPolicy,
)


class CapturingSender:
    def __init__(self) -> None:
        self.code = ""
        self.recipient = ""

    def send(self, *, recipient: str, code: str, expires_at_utc: datetime) -> None:
        self.recipient = recipient
        self.code = code


class FixedSecondFactor:
    def __init__(self, expected: str = "246810") -> None:
        self.expected = expected

    def verify(self, code: str, *, at_utc: datetime) -> bool:
        return code == self.expected


def build_manager() -> tuple[LiveAuthorizationManager, CapturingSender]:
    sender = CapturingSender()
    manager = LiveAuthorizationManager(
        recipient="owner@example.com",
        otp_sender=sender,
        second_factor=FixedSecondFactor(),
        policy=LiveAuthorizationPolicy(
            email_otp_ttl_seconds=120,
            max_email_attempts=3,
            lease_seconds=600,
            absolute_max_lease_seconds=1200,
        ),
    )
    return manager, sender


def test_two_factor_flow_grants_temporary_lease() -> None:
    manager, sender = build_manager()
    now = datetime(2026, 7, 19, 7, 0, tzinfo=UTC)

    assert manager.request_email_otp(now_utc=now) == "EMAIL_OTP_SENT"
    assert sender.recipient == "owner@example.com"
    assert manager.verify_email_otp(sender.code, now_utc=now + timedelta(seconds=10)) == "EMAIL_OTP_VERIFIED"
    assert manager.state.stage == AuthorizationStage.SECOND_FACTOR_PENDING

    assert manager.verify_second_factor("246810", now_utc=now + timedelta(seconds=20)) == "LIVE_AUTHORIZATION_ACTIVE"
    manager.require_active(now_utc=now + timedelta(minutes=5))
    assert manager.state.stage == AuthorizationStage.ACTIVE


def test_wrong_email_otp_revokes_after_attempt_limit() -> None:
    manager, _ = build_manager()
    now = datetime(2026, 7, 19, 7, 0, tzinfo=UTC)
    manager.request_email_otp(now_utc=now)

    for _ in range(2):
        with pytest.raises(RuntimeError, match="invalid email OTP"):
            manager.verify_email_otp("000000", now_utc=now + timedelta(seconds=5))

    with pytest.raises(RuntimeError, match="invalid email OTP"):
        manager.verify_email_otp("000000", now_utc=now + timedelta(seconds=6))
    assert manager.state.stage == AuthorizationStage.REVOKED
    assert manager.state.revocation_reason == "EMAIL_OTP_ATTEMPTS_EXCEEDED"


def test_expired_otp_fails_closed() -> None:
    manager, sender = build_manager()
    now = datetime(2026, 7, 19, 7, 0, tzinfo=UTC)
    manager.request_email_otp(now_utc=now)

    with pytest.raises(RuntimeError, match="expired"):
        manager.verify_email_otp(sender.code, now_utc=now + timedelta(seconds=121))
    assert manager.state.stage == AuthorizationStage.REVOKED


def test_lease_expiry_requires_reauthentication() -> None:
    manager, sender = build_manager()
    now = datetime(2026, 7, 19, 7, 0, tzinfo=UTC)
    manager.request_email_otp(now_utc=now)
    manager.verify_email_otp(sender.code, now_utc=now + timedelta(seconds=1))
    manager.verify_second_factor("246810", now_utc=now + timedelta(seconds=2))

    with pytest.raises(PermissionError, match="not active"):
        manager.require_active(now_utc=now + timedelta(seconds=603))
    assert manager.state.stage == AuthorizationStage.REVOKED
    assert manager.state.revocation_reason == "LEASE_EXPIRED"


def test_operator_can_revoke_immediately() -> None:
    manager, sender = build_manager()
    now = datetime(2026, 7, 19, 7, 0, tzinfo=UTC)
    manager.request_email_otp(now_utc=now)
    manager.verify_email_otp(sender.code, now_utc=now + timedelta(seconds=1))
    manager.verify_second_factor("246810", now_utc=now + timedelta(seconds=2))

    assert manager.revoke("STOP_COMMAND", now_utc=now + timedelta(seconds=3)) == "LIVE_AUTHORIZATION_REVOKED"
    with pytest.raises(PermissionError):
        manager.require_active(now_utc=now + timedelta(seconds=4))
