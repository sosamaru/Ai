from __future__ import annotations

import base64
import hashlib
import hmac
import json
import smtplib
import sqlite3
import struct
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Callable


@dataclass(frozen=True, slots=True)
class SmtpOtpConfig:
    host: str
    port: int
    username: str
    password: str
    sender_email: str
    use_ssl: bool = True
    starttls: bool = False
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.host.strip() or not 1 <= self.port <= 65535:
            raise ValueError("valid SMTP host and port are required")
        if "@" not in self.sender_email:
            raise ValueError("valid SMTP sender email is required")
        if self.use_ssl and self.starttls:
            raise ValueError("use_ssl and starttls are mutually exclusive")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class SmtpOtpSender:
    """Secret-safe SMTP implementation of the OtpSender protocol."""

    def __init__(self, config: SmtpOtpConfig, smtp_factory: Callable[..., object] | None = None) -> None:
        self.config = config
        self._smtp_factory = smtp_factory

    def send(self, *, recipient: str, code: str, expires_at_utc: datetime) -> None:
        if "@" not in recipient:
            raise ValueError("valid OTP recipient is required")
        if len(code) != 6 or not code.isdigit():
            raise ValueError("OTP must be a six-digit string")
        if expires_at_utc.tzinfo is None:
            raise ValueError("expires_at_utc must be timezone-aware")

        message = EmailMessage()
        message["Subject"] = "AiPro LIVE authorization code"
        message["From"] = self.config.sender_email
        message["To"] = recipient
        message.set_content(
            "AiPro LIVE authorization was requested.\n\n"
            f"Verification code: {code}\n"
            f"Expires at: {expires_at_utc.astimezone(UTC).isoformat()}\n\n"
            "Do not share this code. If you did not request authorization, stop the system and rotate credentials."
        )

        factory = self._smtp_factory
        if factory is None:
            factory = smtplib.SMTP_SSL if self.config.use_ssl else smtplib.SMTP
        client = factory(self.config.host, self.config.port, timeout=self.config.timeout_seconds)
        try:
            if self.config.starttls:
                client.starttls()  # type: ignore[attr-defined]
            if self.config.username:
                client.login(self.config.username, self.config.password)  # type: ignore[attr-defined]
            client.send_message(message)  # type: ignore[attr-defined]
        finally:
            try:
                client.quit()  # type: ignore[attr-defined]
            except Exception:
                pass


def _normalize_base32(secret: str) -> bytes:
    normalized = "".join(secret.strip().upper().split())
    if not normalized:
        raise ValueError("TOTP secret is required")
    padding = "=" * ((8 - len(normalized) % 8) % 8)
    try:
        return base64.b32decode(normalized + padding, casefold=True)
    except Exception as exc:
        raise ValueError("invalid Base32 TOTP secret") from exc


class TotpVerifier:
    """RFC 6238-compatible SHA-1 TOTP verifier with a bounded time window."""

    def __init__(self, secret_base32: str, *, digits: int = 6, period_seconds: int = 30, window: int = 1) -> None:
        if digits not in {6, 8}:
            raise ValueError("TOTP digits must be 6 or 8")
        if period_seconds <= 0 or not 0 <= window <= 2:
            raise ValueError("invalid TOTP period or window")
        self._secret = _normalize_base32(secret_base32)
        self.digits = digits
        self.period_seconds = period_seconds
        self.window = window

    def _code_for_counter(self, counter: int) -> str:
        digest = hmac.new(self._secret, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return f"{binary % (10 ** self.digits):0{self.digits}d}"

    def verify(self, code: str, *, at_utc: datetime) -> bool:
        if at_utc.tzinfo is None:
            raise ValueError("at_utc must be timezone-aware")
        normalized = code.strip()
        if len(normalized) != self.digits or not normalized.isdigit():
            return False
        counter = int(at_utc.astimezone(UTC).timestamp()) // self.period_seconds
        return any(
            hmac.compare_digest(normalized, self._code_for_counter(counter + offset))
            for offset in range(-self.window, self.window + 1)
            if counter + offset >= 0
        )


@dataclass(frozen=True, slots=True)
class AuthorizationAuditEvent:
    event: str
    stage: str
    occurred_at_utc: str
    recipient_hash: str
    reason: str = ""

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuthorizationAuditStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS authorization_audit (
                    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fingerprint TEXT NOT NULL UNIQUE,
                    occurred_at_utc TEXT NOT NULL,
                    event TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS authorization_audit_no_update
                BEFORE UPDATE ON authorization_audit
                BEGIN SELECT RAISE(ABORT, 'authorization audit is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS authorization_audit_no_delete
                BEFORE DELETE ON authorization_audit
                BEGIN SELECT RAISE(ABORT, 'authorization audit is immutable'); END;
                """
            )

    def append(self, event: AuthorizationAuditEvent) -> None:
        payload = json.dumps(asdict(event), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                "INSERT INTO authorization_audit (fingerprint, occurred_at_utc, event, payload_json) VALUES (?, ?, ?, ?)",
                (event.fingerprint, event.occurred_at_utc, event.event, payload),
            )


__all__ = [
    "AuthorizationAuditEvent",
    "AuthorizationAuditStore",
    "SmtpOtpConfig",
    "SmtpOtpSender",
    "TotpVerifier",
]
