from __future__ import annotations

import getpass
import hashlib
import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aipro.core.auth_adapters import TotpVerifier
from aipro.sqlite_utils import connect


@dataclass(frozen=True, slots=True)
class TotpVerificationEvidence:
    created_at_utc: str
    enrollment_hash: str
    counter: int
    outcome: str
    reason: str

    @property
    def fingerprint(self) -> str:
        payload = "|".join(
            (
                self.created_at_utc,
                self.enrollment_hash,
                str(self.counter),
                self.outcome,
                self.reason,
            )
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class TotpOperationalStore:
    """Append-only TOTP evidence and replay claims without storing secrets or codes."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute(
                "CREATE TABLE IF NOT EXISTS totp_operational_evidence ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "created_at_utc TEXT NOT NULL, enrollment_hash TEXT NOT NULL, "
                "counter INTEGER NOT NULL, outcome TEXT NOT NULL, reason TEXT NOT NULL, "
                "fingerprint TEXT UNIQUE NOT NULL)"
            )
            db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS totp_counter_once "
                "ON totp_operational_evidence(enrollment_hash, counter) "
                "WHERE outcome = 'accepted'"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS totp_evidence_no_update "
                "BEFORE UPDATE ON totp_operational_evidence "
                "BEGIN SELECT RAISE(ABORT, 'append only'); END"
            )
            db.execute(
                "CREATE TRIGGER IF NOT EXISTS totp_evidence_no_delete "
                "BEFORE DELETE ON totp_operational_evidence "
                "BEGIN SELECT RAISE(ABORT, 'append only'); END"
            )

    def append(self, evidence: TotpVerificationEvidence) -> None:
        parsed = datetime.fromisoformat(evidence.created_at_utc)
        if parsed.tzinfo is None:
            raise ValueError("evidence timestamp must be timezone-aware")
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute(
                "INSERT INTO totp_operational_evidence("
                "created_at_utc, enrollment_hash, counter, outcome, reason, fingerprint"
                ") VALUES (?, ?, ?, ?, ?, ?)",
                (
                    evidence.created_at_utc,
                    evidence.enrollment_hash,
                    evidence.counter,
                    evidence.outcome,
                    evidence.reason,
                    evidence.fingerprint,
                ),
            )

    def accepted_counter_exists(self, *, enrollment_hash: str, counter: int) -> bool:
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            row = db.execute(
                "SELECT 1 FROM totp_operational_evidence "
                "WHERE enrollment_hash = ? AND counter = ? AND outcome = 'accepted' LIMIT 1",
                (enrollment_hash, counter),
            ).fetchone()
        return row is not None

    def count(self) -> int:
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            return int(db.execute("SELECT COUNT(*) FROM totp_operational_evidence").fetchone()[0])


def _enrollment_hash(label: str) -> str:
    normalized = label.strip().casefold()
    if not normalized:
        raise ValueError("TOTP enrollment label is required")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_totp_operationally(
    *,
    verifier: TotpVerifier,
    code: str,
    enrollment_label: str,
    store: TotpOperationalStore,
    at_utc: datetime,
) -> TotpVerificationEvidence:
    if at_utc.tzinfo is None:
        raise ValueError("verification timestamp must be timezone-aware")

    evaluated_at = at_utc.astimezone(UTC)
    enrollment_hash = _enrollment_hash(enrollment_label)
    counter = int(evaluated_at.timestamp()) // verifier.period_seconds

    if store.accepted_counter_exists(enrollment_hash=enrollment_hash, counter=counter):
        evidence = TotpVerificationEvidence(
            created_at_utc=evaluated_at.isoformat(),
            enrollment_hash=enrollment_hash,
            counter=counter,
            outcome="rejected",
            reason="replay_detected",
        )
        store.append(evidence)
        return evidence

    if not verifier.verify(code, at_utc=evaluated_at):
        evidence = TotpVerificationEvidence(
            created_at_utc=evaluated_at.isoformat(),
            enrollment_hash=enrollment_hash,
            counter=counter,
            outcome="rejected",
            reason="invalid_code",
        )
        store.append(evidence)
        return evidence

    evidence = TotpVerificationEvidence(
        created_at_utc=evaluated_at.isoformat(),
        enrollment_hash=enrollment_hash,
        counter=counter,
        outcome="accepted",
        reason="current_code_verified",
    )
    try:
        store.append(evidence)
    except sqlite3.IntegrityError:
        replay = TotpVerificationEvidence(
            created_at_utc=evaluated_at.isoformat(),
            enrollment_hash=enrollment_hash,
            counter=counter,
            outcome="rejected",
            reason="replay_detected",
        )
        store.append(replay)
        return replay
    return evidence


def main() -> int:
    if os.environ.get("AIPRO_TOTP_VERIFY") != "YES":
        print("TOTP verification blocked: set AIPRO_TOTP_VERIFY=YES for a supervised run.")
        return 2

    label = os.environ.get("AIPRO_TOTP_ENROLLMENT_LABEL", "AiPro operator")
    db_path = os.environ.get("AIPRO_TOTP_EVIDENCE_DB", "data/totp_operational_evidence.sqlite3")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    verifier = TotpVerifier.from_env()
    code = getpass.getpass("Current authenticator code: ").strip()
    evidence = verify_totp_operationally(
        verifier=verifier,
        code=code,
        enrollment_label=label,
        store=TotpOperationalStore(db_path),
        at_utc=datetime.now(UTC),
    )
    print(
        "TOTP operational verification "
        f"{evidence.outcome}: {evidence.reason}; fingerprint={evidence.fingerprint}"
    )
    return 0 if evidence.outcome == "accepted" else 1


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "TotpOperationalStore",
    "TotpVerificationEvidence",
    "verify_totp_operationally",
]
