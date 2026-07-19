from __future__ import annotations

import hashlib
import hmac
import secrets
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol


class AuthorizationStage(StrEnum):
    LOCKED = "LOCKED"
    EMAIL_PENDING = "EMAIL_PENDING"
    SECOND_FACTOR_PENDING = "SECOND_FACTOR_PENDING"
    ACTIVE = "ACTIVE"
    REVOKED = "REVOKED"


class OtpSender(Protocol):
    def send(self, *, recipient: str, code: str, expires_at_utc: datetime) -> None: ...


class SecondFactorVerifier(Protocol):
    def verify(self, code: str, *, at_utc: datetime) -> bool: ...


@dataclass(frozen=True, slots=True)
class LiveAuthorizationPolicy:
    email_otp_ttl_seconds: int = 300
    max_email_attempts: int = 5
    lease_seconds: int = 4 * 60 * 60
    absolute_max_lease_seconds: int = 12 * 60 * 60

    def __post_init__(self) -> None:
        if not 60 <= self.email_otp_ttl_seconds <= 900:
            raise ValueError("email OTP TTL must be between 60 and 900 seconds")
        if not 1 <= self.max_email_attempts <= 10:
            raise ValueError("max_email_attempts must be between 1 and 10")
        if not 300 <= self.lease_seconds <= self.absolute_max_lease_seconds:
            raise ValueError("invalid live authorization lease")


@dataclass(frozen=True, slots=True)
class LiveAuthorizationState:
    stage: AuthorizationStage = AuthorizationStage.LOCKED
    recipient_hash: str = ""
    otp_salt: str = ""
    otp_digest: str = ""
    otp_expires_at_utc: str = ""
    failed_attempts: int = 0
    requested_at_utc: str = ""
    activated_at_utc: str = ""
    lease_expires_at_utc: str = ""
    revoked_at_utc: str = ""
    revocation_reason: str = ""

    def is_active(self, *, now_utc: datetime) -> bool:
        if self.stage != AuthorizationStage.ACTIVE or not self.lease_expires_at_utc:
            return False
        return now_utc.astimezone(UTC) < datetime.fromisoformat(self.lease_expires_at_utc).astimezone(UTC)


class LiveAuthorizationManager:
    """Two-factor authorization lease.

    This component grants a temporary operator authorization lease only. It does not
    place orders, change trading mode, or bypass readiness/risk gates.
    """

    def __init__(
        self,
        *,
        recipient: str,
        otp_sender: OtpSender,
        second_factor: SecondFactorVerifier,
        policy: LiveAuthorizationPolicy | None = None,
        state: LiveAuthorizationState | None = None,
    ) -> None:
        if "@" not in recipient or len(recipient.strip()) < 5:
            raise ValueError("a valid email recipient is required")
        self._recipient = recipient.strip().lower()
        self._otp_sender = otp_sender
        self._second_factor = second_factor
        self.policy = policy or LiveAuthorizationPolicy()
        self.state = state or LiveAuthorizationState()

    @staticmethod
    def _digest(code: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}:{code}".encode("utf-8")).hexdigest()

    @property
    def recipient_hash(self) -> str:
        return hashlib.sha256(self._recipient.encode("utf-8")).hexdigest()

    def request_email_otp(self, *, now_utc: datetime | None = None) -> str:
        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        code = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(16)
        expires = now + timedelta(seconds=self.policy.email_otp_ttl_seconds)
        self.state = LiveAuthorizationState(
            stage=AuthorizationStage.EMAIL_PENDING,
            recipient_hash=self.recipient_hash,
            otp_salt=salt,
            otp_digest=self._digest(code, salt),
            otp_expires_at_utc=expires.isoformat(),
            requested_at_utc=now.isoformat(),
        )
        self._otp_sender.send(recipient=self._recipient, code=code, expires_at_utc=expires)
        return "EMAIL_OTP_SENT"

    def verify_email_otp(self, code: str, *, now_utc: datetime | None = None) -> str:
        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        if self.state.stage != AuthorizationStage.EMAIL_PENDING:
            raise RuntimeError("email OTP is not pending")
        if now >= datetime.fromisoformat(self.state.otp_expires_at_utc).astimezone(UTC):
            self.revoke("EMAIL_OTP_EXPIRED", now_utc=now)
            raise RuntimeError("email OTP expired")
        failed = self.state.failed_attempts
        valid = hmac.compare_digest(self._digest(code.strip(), self.state.otp_salt), self.state.otp_digest)
        if not valid:
            failed += 1
            self.state = replace(self.state, failed_attempts=failed)
            if failed >= self.policy.max_email_attempts:
                self.revoke("EMAIL_OTP_ATTEMPTS_EXCEEDED", now_utc=now)
            raise RuntimeError("invalid email OTP")
        self.state = replace(
            self.state,
            stage=AuthorizationStage.SECOND_FACTOR_PENDING,
            otp_salt="",
            otp_digest="",
            otp_expires_at_utc="",
            failed_attempts=0,
        )
        return "EMAIL_OTP_VERIFIED"

    def verify_second_factor(self, code: str, *, now_utc: datetime | None = None) -> str:
        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        if self.state.stage != AuthorizationStage.SECOND_FACTOR_PENDING:
            raise RuntimeError("second factor is not pending")
        if not self._second_factor.verify(code.strip(), at_utc=now):
            raise RuntimeError("invalid second factor")
        expires = now + timedelta(seconds=self.policy.lease_seconds)
        absolute = now + timedelta(seconds=self.policy.absolute_max_lease_seconds)
        if expires > absolute:
            expires = absolute
        self.state = replace(
            self.state,
            stage=AuthorizationStage.ACTIVE,
            activated_at_utc=now.isoformat(),
            lease_expires_at_utc=expires.isoformat(),
        )
        return "LIVE_AUTHORIZATION_ACTIVE"

    def require_active(self, *, now_utc: datetime | None = None) -> None:
        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        if not self.state.is_active(now_utc=now):
            if self.state.stage == AuthorizationStage.ACTIVE:
                self.revoke("LEASE_EXPIRED", now_utc=now)
            raise PermissionError("live authorization is not active")

    def revoke(self, reason: str, *, now_utc: datetime | None = None) -> str:
        now = (now_utc or datetime.now(UTC)).astimezone(UTC)
        self.state = replace(
            self.state,
            stage=AuthorizationStage.REVOKED,
            otp_salt="",
            otp_digest="",
            otp_expires_at_utc="",
            lease_expires_at_utc="",
            revoked_at_utc=now.isoformat(),
            revocation_reason=reason.strip() or "OPERATOR_REVOKED",
        )
        return "LIVE_AUTHORIZATION_REVOKED"


__all__ = [
    "AuthorizationStage",
    "LiveAuthorizationManager",
    "LiveAuthorizationPolicy",
    "LiveAuthorizationState",
    "OtpSender",
    "SecondFactorVerifier",
]
