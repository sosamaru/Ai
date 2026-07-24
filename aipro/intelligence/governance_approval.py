"""Immutable operator-review evidence for PAPER model governance.

The ledger records human decisions about challenger-monitor recommendations. It
never mutates the champion registry, promotes a model, contacts a broker, or
creates PAPER/LIVE order authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
import sqlite3

from aipro.intelligence.challenger_monitor import MonitoringDecision, Recommendation
from aipro.intelligence.classical_ml import ModelDomain


_SCHEMA_VERSION = "paper-governance-approval-v1"


class ReviewOutcome(str, Enum):
    APPROVE = "approve"
    REJECT = "reject"
    DEFER = "defer"


@dataclass(frozen=True)
class ApprovalEvent:
    event_id: str
    domain: ModelDomain
    monitoring_fingerprint: str
    recommendation: Recommendation
    outcome: ReviewOutcome
    reviewer_id: str
    reason: str
    previous_event_id: str | None
    created_at: str
    schema_version: str = _SCHEMA_VERSION
    paper_only: bool = True
    grants_execution_authority: bool = False


class GovernanceApprovalLedger:
    """Append-only SQLite ledger for explicit operator review evidence."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._initialize()

    def record(
        self,
        decision: MonitoringDecision,
        outcome: ReviewOutcome,
        reviewer_id: str,
        reason: str,
    ) -> ApprovalEvent:
        reviewer = reviewer_id.strip()
        normalized_reason = reason.strip()
        if not reviewer:
            raise ValueError("reviewer_id is required")
        if not normalized_reason:
            raise ValueError("review reason is required")
        if len(decision.fingerprint) != 64 or any(
            char not in "0123456789abcdef" for char in decision.fingerprint
        ):
            raise ValueError("monitoring fingerprint must be a lowercase SHA-256 digest")
        if not decision.paper_only:
            raise ValueError("only PAPER monitoring decisions may be reviewed")
        if decision.recommendation is Recommendation.HOLD and outcome is ReviewOutcome.APPROVE:
            raise ValueError("HOLD has no state-changing action to approve")
        if decision.recommendation is Recommendation.ABSTAIN and outcome is ReviewOutcome.APPROVE:
            raise ValueError("ABSTAIN cannot be approved")

        previous = self.latest(decision.domain)
        created_at = datetime.now(timezone.utc).isoformat()
        event_id = self._event_id(
            domain=decision.domain,
            monitoring_fingerprint=decision.fingerprint,
            recommendation=decision.recommendation,
            outcome=outcome,
            reviewer_id=reviewer,
            reason=normalized_reason,
            previous_event_id=previous.event_id if previous else None,
            created_at=created_at,
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT event_id FROM governance_approval_events "
                "WHERE domain = ? ORDER BY sequence_no DESC LIMIT 1",
                (decision.domain.value,),
            ).fetchone()
            expected_previous = latest["event_id"] if latest else None
            if expected_previous != (previous.event_id if previous else None):
                raise RuntimeError("approval ledger changed concurrently")
            duplicate = connection.execute(
                "SELECT event_id FROM governance_approval_events "
                "WHERE monitoring_fingerprint = ? AND reviewer_id = ?",
                (decision.fingerprint, reviewer),
            ).fetchone()
            if duplicate:
                raise ValueError("reviewer already recorded an outcome for this monitoring decision")
            connection.execute(
                """
                INSERT INTO governance_approval_events (
                    event_id, domain, monitoring_fingerprint, recommendation,
                    outcome, reviewer_id, reason, previous_event_id, created_at,
                    schema_version, paper_only, grants_execution_authority
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0)
                """,
                (
                    event_id,
                    decision.domain.value,
                    decision.fingerprint,
                    decision.recommendation.value,
                    outcome.value,
                    reviewer,
                    normalized_reason,
                    previous.event_id if previous else None,
                    created_at,
                    _SCHEMA_VERSION,
                ),
            )
        return self.get(event_id)  # type: ignore[return-value]

    def latest(self, domain: ModelDomain) -> ApprovalEvent | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM governance_approval_events "
                "WHERE domain = ? ORDER BY sequence_no DESC LIMIT 1",
                (domain.value,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    def history(self, domain: ModelDomain) -> tuple[ApprovalEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM governance_approval_events "
                "WHERE domain = ? ORDER BY sequence_no ASC",
                (domain.value,),
            ).fetchall()
        return tuple(self._row_to_event(row) for row in rows)

    def get(self, event_id: str) -> ApprovalEvent | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM governance_approval_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
        return self._row_to_event(row) if row else None

    def verify_chain(self, domain: ModelDomain) -> bool:
        previous_id: str | None = None
        for event in self.history(domain):
            if event.previous_event_id != previous_id:
                return False
            expected = self._event_id(
                domain=event.domain,
                monitoring_fingerprint=event.monitoring_fingerprint,
                recommendation=event.recommendation,
                outcome=event.outcome,
                reviewer_id=event.reviewer_id,
                reason=event.reason,
                previous_event_id=event.previous_event_id,
                created_at=event.created_at,
            )
            if expected != event.event_id:
                return False
            if not event.paper_only or event.grants_execution_authority:
                return False
            previous_id = event.event_id
        return True

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS governance_approval_events (
                    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL CHECK(domain IN ('crypto', 'us_stock')),
                    monitoring_fingerprint TEXT NOT NULL,
                    recommendation TEXT NOT NULL CHECK(recommendation IN (
                        'hold', 'review_replacement', 'review_rollback',
                        'deactivate', 'abstain'
                    )),
                    outcome TEXT NOT NULL CHECK(outcome IN ('approve', 'reject', 'defer')),
                    reviewer_id TEXT NOT NULL CHECK(length(trim(reviewer_id)) > 0),
                    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
                    previous_event_id TEXT,
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    paper_only INTEGER NOT NULL CHECK(paper_only = 1),
                    grants_execution_authority INTEGER NOT NULL CHECK(grants_execution_authority = 0),
                    UNIQUE(monitoring_fingerprint, reviewer_id)
                );
                CREATE TRIGGER IF NOT EXISTS governance_approval_no_update
                BEFORE UPDATE ON governance_approval_events BEGIN
                    SELECT RAISE(ABORT, 'governance approval ledger is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS governance_approval_no_delete
                BEFORE DELETE ON governance_approval_events BEGIN
                    SELECT RAISE(ABORT, 'governance approval ledger is append-only');
                END;
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _event_id(
        *,
        domain: ModelDomain,
        monitoring_fingerprint: str,
        recommendation: Recommendation,
        outcome: ReviewOutcome,
        reviewer_id: str,
        reason: str,
        previous_event_id: str | None,
        created_at: str,
    ) -> str:
        payload = {
            "domain": domain.value,
            "monitoring_fingerprint": monitoring_fingerprint,
            "recommendation": recommendation.value,
            "outcome": outcome.value,
            "reviewer_id": reviewer_id,
            "reason": reason,
            "previous_event_id": previous_event_id,
            "created_at": created_at,
            "schema_version": _SCHEMA_VERSION,
            "paper_only": True,
            "grants_execution_authority": False,
        }
        return sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> ApprovalEvent:
        return ApprovalEvent(
            event_id=row["event_id"],
            domain=ModelDomain(row["domain"]),
            monitoring_fingerprint=row["monitoring_fingerprint"],
            recommendation=Recommendation(row["recommendation"]),
            outcome=ReviewOutcome(row["outcome"]),
            reviewer_id=row["reviewer_id"],
            reason=row["reason"],
            previous_event_id=row["previous_event_id"],
            created_at=row["created_at"],
            schema_version=row["schema_version"],
            paper_only=bool(row["paper_only"]),
            grants_execution_authority=bool(row["grants_execution_authority"]),
        )
