from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


_ALLOWED_ATTESTATIONS = {
    "mailbox_arrival_confirmed",
    "totp_recovery_stored_offline",
    "upbit_preflight_supervised",
}


@dataclass(frozen=True, slots=True)
class OperatorAttestation:
    created_at_utc: str
    kind: str
    operator_hash: str
    evidence_note_hash: str

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OperatorAttestationStore:
    """Append-only manual attestations. Attestations grant no trading authority."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS operator_attestations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at_utc TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    operator_hash TEXT NOT NULL,
                    evidence_note_hash TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS operator_attestations_no_update
                BEFORE UPDATE ON operator_attestations BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER IF NOT EXISTS operator_attestations_no_delete
                BEFORE DELETE ON operator_attestations BEGIN SELECT RAISE(ABORT, 'append only'); END;
                """
            )

    def append(self, attestation: OperatorAttestation) -> str:
        created = datetime.fromisoformat(attestation.created_at_utc)
        if created.tzinfo is None:
            raise ValueError("created_at_utc must be timezone-aware")
        if attestation.kind not in _ALLOWED_ATTESTATIONS:
            raise ValueError("unsupported attestation kind")
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO operator_attestations(created_at_utc,kind,operator_hash,evidence_note_hash,fingerprint) VALUES(?,?,?,?,?)",
                (
                    attestation.created_at_utc,
                    attestation.kind,
                    attestation.operator_hash,
                    attestation.evidence_note_hash,
                    attestation.fingerprint,
                ),
            )
        return attestation.fingerprint


def create_attestation(*, kind: str, operator_label: str, evidence_note: str, created_at_utc: datetime) -> OperatorAttestation:
    if kind not in _ALLOWED_ATTESTATIONS:
        raise ValueError("unsupported attestation kind")
    if created_at_utc.tzinfo is None:
        raise ValueError("created_at_utc must be timezone-aware")
    operator = operator_label.strip().casefold()
    note = evidence_note.strip()
    if not operator or not note:
        raise ValueError("operator label and evidence note are required")
    return OperatorAttestation(
        created_at_utc=created_at_utc.astimezone(UTC).isoformat(),
        kind=kind,
        operator_hash=hashlib.sha256(operator.encode("utf-8")).hexdigest(),
        evidence_note_hash=hashlib.sha256(note.encode("utf-8")).hexdigest(),
    )


@dataclass(frozen=True, slots=True)
class OperationalReadinessReview:
    evaluated_at_utc: str
    smtp_delivery_evidence: bool
    totp_acceptance_evidence: bool
    alpaca_paper_qualifying: bool
    mailbox_arrival_attested: bool
    recovery_storage_attested: bool
    upbit_preflight_attested: bool
    status: str
    blockers: tuple[str, ...]
    source_fingerprints: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class OperationalReadinessReviewStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS operational_readiness_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluated_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS operational_reviews_no_update
                BEFORE UPDATE ON operational_readiness_reviews BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER IF NOT EXISTS operational_reviews_no_delete
                BEFORE DELETE ON operational_readiness_reviews BEGIN SELECT RAISE(ABORT, 'append only'); END;
                """
            )

    def append(self, review: OperationalReadinessReview) -> str:
        payload = json.dumps(asdict(review), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO operational_readiness_reviews(evaluated_at_utc,payload_json,fingerprint) VALUES(?,?,?)",
                (review.evaluated_at_utc, payload, review.fingerprint),
            )
        return review.fingerprint


def _latest_row(path: str | Path, query: str) -> tuple[Any, ...] | None:
    try:
        with sqlite3.connect(str(path)) as db:
            return db.execute(query).fetchone()
    except sqlite3.Error:
        return None


def build_operational_readiness_review(
    *,
    smtp_db: str | Path,
    totp_db: str | Path,
    paper_report_db: str | Path,
    attestation_db: str | Path,
    review_store: OperationalReadinessReviewStore,
    evaluated_at_utc: datetime,
) -> OperationalReadinessReview:
    if evaluated_at_utc.tzinfo is None:
        raise ValueError("evaluated_at_utc must be timezone-aware")

    smtp = _latest_row(smtp_db, "SELECT delivered,fingerprint FROM smtp_verification_evidence ORDER BY id DESC LIMIT 1")
    totp = _latest_row(totp_db, "SELECT outcome,fingerprint FROM totp_operational_evidence ORDER BY id DESC LIMIT 1")
    paper = _latest_row(paper_report_db, "SELECT payload_json,fingerprint FROM paper_readiness_reports ORDER BY id DESC LIMIT 1")

    smtp_ok = bool(smtp and int(smtp[0]) == 1)
    totp_ok = bool(totp and str(totp[0]) == "accepted")
    paper_ok = False
    if paper:
        payload = json.loads(str(paper[0]))
        paper_ok = bool(payload.get("qualifying", False))

    attestations: set[str] = set()
    attestation_fingerprints: list[str] = []
    try:
        with sqlite3.connect(str(attestation_db)) as db:
            rows = db.execute("SELECT kind,fingerprint FROM operator_attestations ORDER BY id ASC").fetchall()
        for kind, fingerprint in rows:
            attestations.add(str(kind))
            attestation_fingerprints.append(str(fingerprint))
    except sqlite3.Error:
        pass

    checks = {
        "SMTP_DELIVERY_EVIDENCE_MISSING": smtp_ok,
        "TOTP_ACCEPTANCE_EVIDENCE_MISSING": totp_ok,
        "ALPACA_30_DAY_QUALIFYING_EVIDENCE_MISSING": paper_ok,
        "MAILBOX_ARRIVAL_ATTESTATION_MISSING": "mailbox_arrival_confirmed" in attestations,
        "TOTP_RECOVERY_STORAGE_ATTESTATION_MISSING": "totp_recovery_stored_offline" in attestations,
        "UPBIT_PREFLIGHT_ATTESTATION_MISSING": "upbit_preflight_supervised" in attestations,
    }
    blockers = tuple(key for key, passed in checks.items() if not passed)
    source_fingerprints = tuple(
        item
        for item in (
            str(smtp[1]) if smtp else "",
            str(totp[1]) if totp else "",
            str(paper[1]) if paper else "",
            *attestation_fingerprints,
        )
        if item
    )
    review = OperationalReadinessReview(
        evaluated_at_utc=evaluated_at_utc.astimezone(UTC).isoformat(),
        smtp_delivery_evidence=smtp_ok,
        totp_acceptance_evidence=totp_ok,
        alpaca_paper_qualifying=paper_ok,
        mailbox_arrival_attested="mailbox_arrival_confirmed" in attestations,
        recovery_storage_attested="totp_recovery_stored_offline" in attestations,
        upbit_preflight_attested="upbit_preflight_supervised" in attestations,
        status="READY_FOR_INDEPENDENT_REVIEW" if not blockers else "NOT_READY",
        blockers=blockers,
        source_fingerprints=source_fingerprints,
    )
    review_store.append(review)
    return review


__all__ = [
    "OperationalReadinessReview",
    "OperationalReadinessReviewStore",
    "OperatorAttestation",
    "OperatorAttestationStore",
    "build_operational_readiness_review",
    "create_attestation",
]
