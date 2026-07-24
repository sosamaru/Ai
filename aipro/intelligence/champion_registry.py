"""Immutable PAPER champion activation and rollback registry.

The registry records governance evidence only. It does not load, serve, or train
models and has no broker, order, LIVE-mode, or authorization authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Iterable

from aipro.intelligence.classical_ml import ModelDomain
from aipro.intelligence.model_champion import ChampionDecision


_SCHEMA_VERSION = "paper-champion-registry-v1"
_ALLOWED_ACTIONS = {"ACTIVATE", "REPLACE", "ROLLBACK", "DEACTIVATE"}


@dataclass(frozen=True)
class ChampionRegistryEvent:
    event_id: str
    domain: ModelDomain
    action: str
    candidate_name: str | None
    candidate_fingerprint: str | None
    decision_fingerprint: str | None
    previous_event_id: str | None
    reason: str
    created_at: str
    schema_version: str = _SCHEMA_VERSION
    paper_only: bool = True


class ChampionRegistry:
    """Append-only SQLite registry with per-domain champion history."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = str(database_path)
        self._initialize()

    def activate(self, decision: ChampionDecision, reason: str) -> ChampionRegistryEvent:
        if not decision.approved or decision.champion is None:
            raise ValueError("only an approved champion decision can be activated")
        current = self.current(decision.domain)
        if current and current.candidate_fingerprint == decision.champion.fingerprint:
            raise ValueError("candidate is already the active champion")
        action = "REPLACE" if current else "ACTIVATE"
        return self._append(
            domain=decision.domain,
            action=action,
            candidate_name=decision.champion.spec.name,
            candidate_fingerprint=decision.champion.fingerprint,
            decision_fingerprint=decision.fingerprint,
            previous_event_id=current.event_id if current else None,
            reason=reason,
        )

    def rollback(self, domain: ModelDomain, target_event_id: str, reason: str) -> ChampionRegistryEvent:
        target = self.get(target_event_id)
        if target is None:
            raise ValueError("rollback target does not exist")
        if target.domain is not domain:
            raise ValueError("rollback target domain mismatch")
        if target.candidate_fingerprint is None or target.action == "DEACTIVATE":
            raise ValueError("rollback target has no champion candidate")
        current = self.current(domain)
        if current and current.event_id == target.event_id:
            raise ValueError("rollback target is already active")
        return self._append(
            domain=domain,
            action="ROLLBACK",
            candidate_name=target.candidate_name,
            candidate_fingerprint=target.candidate_fingerprint,
            decision_fingerprint=target.decision_fingerprint,
            previous_event_id=current.event_id if current else None,
            reason=reason,
        )

    def deactivate(self, domain: ModelDomain, reason: str) -> ChampionRegistryEvent:
        current = self.current(domain)
        if current is None:
            raise ValueError("domain has no active champion")
        return self._append(
            domain=domain,
            action="DEACTIVATE",
            candidate_name=None,
            candidate_fingerprint=None,
            decision_fingerprint=None,
            previous_event_id=current.event_id,
            reason=reason,
        )

    def current(self, domain: ModelDomain) -> ChampionRegistryEvent | None:
        events = self.history(domain)
        if not events or events[-1].action == "DEACTIVATE":
            return None
        return events[-1]

    def history(self, domain: ModelDomain) -> tuple[ChampionRegistryEvent, ...]:
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT * FROM champion_events WHERE domain = ? ORDER BY sequence_no ASC",
                (domain.value,),
            ).fetchall()
        return tuple(self._row_to_event(row) for row in rows)

    def get(self, event_id: str) -> ChampionRegistryEvent | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM champion_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return self._row_to_event(row) if row else None

    def verify_chain(self, domain: ModelDomain) -> bool:
        previous_id: str | None = None
        for event in self.history(domain):
            if event.previous_event_id != previous_id:
                return False
            if event.event_id != self._event_id(
                event.domain,
                event.action,
                event.candidate_name,
                event.candidate_fingerprint,
                event.decision_fingerprint,
                event.previous_event_id,
                event.reason,
                event.created_at,
            ):
                return False
            previous_id = event.event_id
        return True

    def _append(
        self,
        *,
        domain: ModelDomain,
        action: str,
        candidate_name: str | None,
        candidate_fingerprint: str | None,
        decision_fingerprint: str | None,
        previous_event_id: str | None,
        reason: str,
    ) -> ChampionRegistryEvent:
        if action not in _ALLOWED_ACTIONS:
            raise ValueError("unsupported registry action")
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("registry reason is required")
        created_at = datetime.now(timezone.utc).isoformat()
        event_id = self._event_id(
            domain,
            action,
            candidate_name,
            candidate_fingerprint,
            decision_fingerprint,
            previous_event_id,
            normalized_reason,
            created_at,
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            latest = connection.execute(
                "SELECT event_id FROM champion_events WHERE domain = ? ORDER BY sequence_no DESC LIMIT 1",
                (domain.value,),
            ).fetchone()
            expected_previous = latest["event_id"] if latest else None
            if expected_previous != previous_event_id:
                raise RuntimeError("champion registry changed concurrently")
            connection.execute(
                """
                INSERT INTO champion_events (
                    event_id, domain, action, candidate_name, candidate_fingerprint,
                    decision_fingerprint, previous_event_id, reason, created_at,
                    schema_version, paper_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                """,
                (
                    event_id,
                    domain.value,
                    action,
                    candidate_name,
                    candidate_fingerprint,
                    decision_fingerprint,
                    previous_event_id,
                    normalized_reason,
                    created_at,
                    _SCHEMA_VERSION,
                ),
            )
        return self.get(event_id)  # type: ignore[return-value]

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS champion_events (
                    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    domain TEXT NOT NULL CHECK(domain IN ('crypto', 'us_stock')),
                    action TEXT NOT NULL CHECK(action IN ('ACTIVATE', 'REPLACE', 'ROLLBACK', 'DEACTIVATE')),
                    candidate_name TEXT,
                    candidate_fingerprint TEXT,
                    decision_fingerprint TEXT,
                    previous_event_id TEXT,
                    reason TEXT NOT NULL CHECK(length(trim(reason)) > 0),
                    created_at TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    paper_only INTEGER NOT NULL CHECK(paper_only = 1)
                );
                CREATE TRIGGER IF NOT EXISTS champion_events_no_update
                BEFORE UPDATE ON champion_events BEGIN
                    SELECT RAISE(ABORT, 'champion registry is append-only');
                END;
                CREATE TRIGGER IF NOT EXISTS champion_events_no_delete
                BEFORE DELETE ON champion_events BEGIN
                    SELECT RAISE(ABORT, 'champion registry is append-only');
                END;
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _event_id(
        domain: ModelDomain,
        action: str,
        candidate_name: str | None,
        candidate_fingerprint: str | None,
        decision_fingerprint: str | None,
        previous_event_id: str | None,
        reason: str,
        created_at: str,
    ) -> str:
        payload = {
            "domain": domain.value,
            "action": action,
            "candidate_name": candidate_name,
            "candidate_fingerprint": candidate_fingerprint,
            "decision_fingerprint": decision_fingerprint,
            "previous_event_id": previous_event_id,
            "reason": reason,
            "created_at": created_at,
            "schema_version": _SCHEMA_VERSION,
            "paper_only": True,
        }
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

    @staticmethod
    def _row_to_event(row: sqlite3.Row) -> ChampionRegistryEvent:
        return ChampionRegistryEvent(
            event_id=row["event_id"],
            domain=ModelDomain(row["domain"]),
            action=row["action"],
            candidate_name=row["candidate_name"],
            candidate_fingerprint=row["candidate_fingerprint"],
            decision_fingerprint=row["decision_fingerprint"],
            previous_event_id=row["previous_event_id"],
            reason=row["reason"],
            created_at=row["created_at"],
            schema_version=row["schema_version"],
            paper_only=bool(row["paper_only"]),
        )
