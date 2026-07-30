from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Protocol

from aipro.core.auth_adapters import SmtpOtpSender
from aipro.sqlite_utils import connect


class OtpSender(Protocol):
    def send(self, *, recipient: str, code: str, expires_at_utc: datetime) -> None: ...


@dataclass(frozen=True, slots=True)
class SmtpVerificationResult:
    attempted_at_utc: str
    recipient_hash: str
    delivered: bool
    provider: str
    reason: str

    @property
    def fingerprint(self) -> str:
        payload = "|".join(
            (
                self.attempted_at_utc,
                self.recipient_hash,
                "1" if self.delivered else "0",
                self.provider,
                self.reason,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SmtpVerificationEvidenceStore:
    """Append-only SMTP verification evidence without recipient or OTP plaintext."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute(
                "CREATE TABLE IF NOT EXISTS smtp_verification_evidence ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "attempted_at_utc TEXT NOT NULL, "
                "recipient_hash TEXT NOT NULL, "
                "delivered INTEGER NOT NULL CHECK(delivered IN (0, 1)), "
                "provider TEXT NOT NULL, "
                "reason TEXT NOT NULL, "
                "fingerprint TEXT UNIQUE NOT NULL)"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS smtp_verification_no_update "
                "BEFORE UPDATE ON smtp_verification_evidence "
                "BEGIN SELECT RAISE(ABORT, 'append only'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS smtp_verification_no_delete "
                "BEFORE DELETE ON smtp_verification_evidence "
                "BEGIN SELECT RAISE(ABORT, 'append only'); END"
            )

    def append(self, result: SmtpVerificationResult) -> None:
        attempted_at = datetime.fromisoformat(result.attempted_at_utc)
        if attempted_at.tzinfo is None:
            raise ValueError("attempted_at_utc must be timezone-aware")
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute(
                "INSERT INTO smtp_verification_evidence("
                "attempted_at_utc, recipient_hash, delivered, provider, reason, fingerprint"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (
                    result.attempted_at_utc,
                    result.recipient_hash,
                    int(result.delivered),
                    result.provider,
                    result.reason,
                    result.fingerprint,
                ),
            )

    def count(self) -> int:
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            return int(db.execute("SELECT COUNT(*) FROM smtp_verification_evidence").fetchone()[0])


def _hash_recipient(recipient: str) -> str:
    normalized = recipient.strip().lower()
    if "@" not in normalized:
        raise ValueError("valid verification recipient is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def run_smtp_verification(
    *,
    sender: OtpSender,
    recipient: str,
    evidence_store: SmtpVerificationEvidenceStore,
    now_utc: datetime | None = None,
    provider: str = "smtp",
) -> SmtpVerificationResult:
    attempted_at = now_utc or datetime.now(UTC)
    if attempted_at.tzinfo is None:
        raise ValueError("now_utc must be timezone-aware")
    if not provider.strip():
        raise ValueError("provider is required")

    recipient_hash = _hash_recipient(recipient)
    code = f"{secrets.randbelow(1_000_000):06d}"
    expires_at = attempted_at.astimezone(UTC) + timedelta(minutes=5)

    delivered = False
    reason = "delivery_failed"
    try:
        sender.send(recipient=recipient, code=code, expires_at_utc=expires_at)
        delivered = True
        reason = "delivery_accepted"
    except Exception as exc:
        reason = f"delivery_failed:{type(exc).__name__}"

    result = SmtpVerificationResult(
        attempted_at_utc=attempted_at.astimezone(UTC).isoformat(),
        recipient_hash=recipient_hash,
        delivered=delivered,
        provider=provider.strip().lower(),
        reason=reason,
    )
    evidence_store.append(result)
    return result


def main() -> int:
    if os.environ.get("AIPRO_SMTP_VERIFY", "") != "YES":
        raise RuntimeError("set AIPRO_SMTP_VERIFY=YES for an explicit supervised verification")

    recipient = os.environ["AIPRO_SMTP_VERIFY_RECIPIENT"]
    evidence_path = os.environ.get(
        "AIPRO_SMTP_VERIFY_DB",
        "data/smtp_verification_evidence.sqlite3",
    )
    Path(evidence_path).parent.mkdir(parents=True, exist_ok=True)

    result = run_smtp_verification(
        sender=SmtpOtpSender.from_env(),
        recipient=recipient,
        evidence_store=SmtpVerificationEvidenceStore(evidence_path),
        provider=os.environ.get("AIPRO_SMTP_PROVIDER", "smtp"),
    )
    print(
        {
            "delivered": result.delivered,
            "attempted_at_utc": result.attempted_at_utc,
            "recipient_hash": result.recipient_hash,
            "provider": result.provider,
            "reason": result.reason,
            "fingerprint": result.fingerprint,
        }
    )
    return 0 if result.delivered else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "SmtpVerificationEvidenceStore",
    "SmtpVerificationResult",
    "run_smtp_verification",
]
