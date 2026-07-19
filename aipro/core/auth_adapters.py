from __future__ import annotations

import base64
import hashlib
import hmac
import os
import smtplib
import sqlite3
import struct
from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from pathlib import Path


class SmtpOtpSender:
    """SMTP OTP sender configured only from explicit values or environment secrets."""

    def __init__(self, *, host: str, port: int, username: str, password: str, sender: str, use_starttls: bool = True, timeout_sec: float = 10.0) -> None:
        if not host.strip() or port <= 0 or not username or not password:
            raise ValueError("valid SMTP configuration is required")
        if "@" not in sender:
            raise ValueError("valid sender email is required")
        self.host = host.strip()
        self.port = port
        self.username = username
        self.password = password
        self.sender = sender.strip()
        self.use_starttls = use_starttls
        self.timeout_sec = timeout_sec

    @classmethod
    def from_env(cls) -> "SmtpOtpSender":
        username = os.environ["AIPRO_SMTP_USERNAME"]
        return cls(
            host=os.environ["AIPRO_SMTP_HOST"],
            port=int(os.environ.get("AIPRO_SMTP_PORT", "587")),
            username=username,
            password=os.environ["AIPRO_SMTP_PASSWORD"],
            sender=os.environ.get("AIPRO_SMTP_SENDER", username),
            use_starttls=os.environ.get("AIPRO_SMTP_STARTTLS", "1") == "1",
        )

    def send(self, *, recipient: str, code: str, expires_at_utc: datetime) -> None:
        if "@" not in recipient or len(code) != 6 or not code.isdigit():
            raise ValueError("invalid OTP delivery request")
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = "AiPro LIVE authorization code"
        message.set_content(
            "AiPro LIVE authorization was requested.\n\n"
            f"Verification code: {code}\n"
            f"Expires at: {expires_at_utc.astimezone(UTC).isoformat()}\n\n"
            "Do not share this code. If this was not you, stop AiPro and rotate credentials."
        )
        with smtplib.SMTP(self.host, self.port, timeout=self.timeout_sec) as client:
            if self.use_starttls:
                client.starttls()
            client.login(self.username, self.password)
            client.send_message(message)


class TotpVerifier:
    """RFC 6238 SHA-1 TOTP verifier without external dependencies."""

    def __init__(self, secret_base32: str, *, period_seconds: int = 30, digits: int = 6, window: int = 1) -> None:
        cleaned = "".join(secret_base32.upper().split())
        if not cleaned:
            raise ValueError("TOTP secret is required")
        try:
            self._secret = base64.b32decode(cleaned + "=" * ((8 - len(cleaned) % 8) % 8), casefold=True)
        except Exception as exc:
            raise ValueError("invalid base32 TOTP secret") from exc
        if period_seconds <= 0 or digits not in (6, 8) or not 0 <= window <= 2:
            raise ValueError("invalid TOTP policy")
        self.period_seconds = period_seconds
        self.digits = digits
        self.window = window

    @classmethod
    def from_env(cls) -> "TotpVerifier":
        return cls(os.environ["AIPRO_TOTP_SECRET"])

    def _code_for_counter(self, counter: int) -> str:
        digest = hmac.new(self._secret, struct.pack(">Q", counter), hashlib.sha1).digest()
        offset = digest[-1] & 0x0F
        value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
        return str(value % (10**self.digits)).zfill(self.digits)

    def verify(self, code: str, *, at_utc: datetime) -> bool:
        normalized = code.strip()
        if at_utc.tzinfo is None or len(normalized) != self.digits or not normalized.isdigit():
            return False
        counter = int(at_utc.astimezone(UTC).timestamp()) // self.period_seconds
        return any(hmac.compare_digest(normalized, self._code_for_counter(counter + delta)) for delta in range(-self.window, self.window + 1))


@dataclass(frozen=True, slots=True)
class AuthorizationAuditEvent:
    event_type: str
    created_at_utc: str
    stage: str
    recipient_hash: str
    reason: str = ""

    @property
    def fingerprint(self) -> str:
        payload = "|".join((self.event_type, self.created_at_utc, self.stage, self.recipient_hash, self.reason))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class AuthorizationAuditStore:
    """Append-only authorization evidence. OTP values and secrets are never persisted."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS authorization_audit (id INTEGER PRIMARY KEY AUTOINCREMENT, event_type TEXT NOT NULL, created_at_utc TEXT NOT NULL, stage TEXT NOT NULL, recipient_hash TEXT NOT NULL, reason TEXT NOT NULL, fingerprint TEXT UNIQUE NOT NULL)")
            db.execute("CREATE TRIGGER IF NOT EXISTS authorization_audit_no_update BEFORE UPDATE ON authorization_audit BEGIN SELECT RAISE(ABORT, 'append only'); END")
            db.execute("CREATE TRIGGER IF NOT EXISTS authorization_audit_no_delete BEFORE DELETE ON authorization_audit BEGIN SELECT RAISE(ABORT, 'append only'); END")

    def append(self, event: AuthorizationAuditEvent) -> None:
        parsed = datetime.fromisoformat(event.created_at_utc)
        if parsed.tzinfo is None:
            raise ValueError("audit timestamp must be timezone-aware")
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT INTO authorization_audit(event_type, created_at_utc, stage, recipient_hash, reason, fingerprint) VALUES (?, ?, ?, ?, ?, ?)", (event.event_type, event.created_at_utc, event.stage, event.recipient_hash, event.reason, event.fingerprint))

    def count(self) -> int:
        with sqlite3.connect(self.path) as db:
            return int(db.execute("SELECT COUNT(*) FROM authorization_audit").fetchone()[0])


__all__ = ["AuthorizationAuditEvent", "AuthorizationAuditStore", "SmtpOtpSender", "TotpVerifier"]
