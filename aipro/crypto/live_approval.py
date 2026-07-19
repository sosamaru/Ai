from __future__ import annotations

import hashlib
import json
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

_REQUESTED = "REQUESTED"
_CONFIRMED = "CONFIRMED"
_ACTIVE = "ACTIVE"
_EXPIRED = "EXPIRED"
_REVOKED = "REVOKED"
_TERMINAL = frozenset({_ACTIVE, _EXPIRED, _REVOKED})


@dataclass(frozen=True, slots=True)
class LiveApprovalState:
    approval_id: str
    state: str
    requested_at_utc: str
    expires_at_utc: str
    confirmed_at_utc: str | None
    activated_at_utc: str | None
    readiness_fingerprint: str
    operator_fingerprint: str

    def is_expired(self, *, now: datetime | None = None) -> bool:
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None:
            raise ValueError("expiration reference must be timezone-aware")
        return reference.astimezone(UTC) >= datetime.fromisoformat(self.expires_at_utc).astimezone(UTC)


class LiveApprovalError(RuntimeError):
    pass


class LiveApprovalStore:
    """Persistent, crypto-only approval state. This does not submit orders."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS crypto_live_approval (
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id = 1),
                    approval_id TEXT NOT NULL,
                    state TEXT NOT NULL,
                    requested_at_utc TEXT NOT NULL,
                    expires_at_utc TEXT NOT NULL,
                    confirmed_at_utc TEXT,
                    activated_at_utc TEXT,
                    readiness_fingerprint TEXT NOT NULL CHECK(length(readiness_fingerprint) = 64),
                    operator_fingerprint TEXT NOT NULL CHECK(length(operator_fingerprint) = 64),
                    updated_at_utc TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS crypto_live_approval_audit (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    approval_id TEXT NOT NULL,
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    occurred_at_utc TEXT NOT NULL,
                    event_fingerprint TEXT NOT NULL UNIQUE CHECK(length(event_fingerprint) = 64)
                )
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS crypto_live_approval_audit_no_update
                BEFORE UPDATE ON crypto_live_approval_audit
                BEGIN
                    SELECT RAISE(ABORT, 'approval audit is immutable');
                END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS crypto_live_approval_audit_no_delete
                BEFORE DELETE ON crypto_live_approval_audit
                BEGIN
                    SELECT RAISE(ABORT, 'approval audit is immutable');
                END
                """
            )

    @staticmethod
    def _validate_now(now: datetime | None) -> datetime:
        value = now or datetime.now(UTC)
        if value.tzinfo is None:
            raise ValueError("approval timestamp must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _fingerprint_operator(operator_id: str) -> str:
        normalized = operator_id.strip()
        if not normalized:
            raise ValueError("operator_id is required")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _audit(
        self,
        connection: sqlite3.Connection,
        *,
        approval_id: str,
        from_state: str | None,
        to_state: str,
        reason: str,
        occurred_at: datetime,
    ) -> None:
        payload = json.dumps(
            {
                "approval_id": approval_id,
                "from_state": from_state,
                "to_state": to_state,
                "reason": reason,
                "occurred_at_utc": occurred_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        connection.execute(
            """
            INSERT INTO crypto_live_approval_audit (
                approval_id, from_state, to_state, reason,
                occurred_at_utc, event_fingerprint
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                approval_id,
                from_state,
                to_state,
                reason,
                occurred_at.isoformat(),
                hashlib.sha256(payload.encode("utf-8")).hexdigest(),
            ),
        )

    def _read(self, connection: sqlite3.Connection) -> LiveApprovalState | None:
        row = connection.execute(
            """
            SELECT approval_id, state, requested_at_utc, expires_at_utc,
                   confirmed_at_utc, activated_at_utc,
                   readiness_fingerprint, operator_fingerprint
            FROM crypto_live_approval WHERE singleton_id = 1
            """
        ).fetchone()
        if row is None:
            return None
        return LiveApprovalState(**dict(row))

    def current(self, *, now: datetime | None = None) -> LiveApprovalState | None:
        reference = self._validate_now(now)
        with self._connect() as connection:
            state = self._read(connection)
            if state is None or state.state in _TERMINAL or not state.is_expired(now=reference):
                return state
            connection.execute(
                "UPDATE crypto_live_approval SET state = ?, updated_at_utc = ? WHERE singleton_id = 1",
                (_EXPIRED, reference.isoformat()),
            )
            self._audit(
                connection,
                approval_id=state.approval_id,
                from_state=state.state,
                to_state=_EXPIRED,
                reason="approval window expired",
                occurred_at=reference,
            )
            return self._read(connection)

    def request(
        self,
        *,
        operator_id: str,
        readiness_fingerprint: str,
        readiness_passed: bool,
        halted: bool,
        ttl_seconds: int = 300,
        now: datetime | None = None,
    ) -> LiveApprovalState:
        reference = self._validate_now(now)
        if not readiness_passed:
            raise LiveApprovalError("readiness gate must PASS before approval request")
        if halted:
            raise LiveApprovalError("HALTED state blocks live approval")
        if len(readiness_fingerprint) != 64:
            raise ValueError("readiness_fingerprint must be a SHA-256 hex digest")
        if ttl_seconds < 30 or ttl_seconds > 900:
            raise ValueError("ttl_seconds must be between 30 and 900")
        operator_fingerprint = self._fingerprint_operator(operator_id)
        approval_id = secrets.token_urlsafe(18)
        expires_at = reference + timedelta(seconds=ttl_seconds)
        with self._connect() as connection:
            previous = self._read(connection)
            if previous is not None and previous.state in {_REQUESTED, _CONFIRMED} and not previous.is_expired(now=reference):
                raise LiveApprovalError("an unexpired approval sequence already exists")
            connection.execute(
                """
                INSERT INTO crypto_live_approval (
                    singleton_id, approval_id, state, requested_at_utc,
                    expires_at_utc, confirmed_at_utc, activated_at_utc,
                    readiness_fingerprint, operator_fingerprint, updated_at_utc
                ) VALUES (1, ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                ON CONFLICT(singleton_id) DO UPDATE SET
                    approval_id = excluded.approval_id,
                    state = excluded.state,
                    requested_at_utc = excluded.requested_at_utc,
                    expires_at_utc = excluded.expires_at_utc,
                    confirmed_at_utc = NULL,
                    activated_at_utc = NULL,
                    readiness_fingerprint = excluded.readiness_fingerprint,
                    operator_fingerprint = excluded.operator_fingerprint,
                    updated_at_utc = excluded.updated_at_utc
                """,
                (
                    approval_id,
                    _REQUESTED,
                    reference.isoformat(),
                    expires_at.isoformat(),
                    readiness_fingerprint,
                    operator_fingerprint,
                    reference.isoformat(),
                ),
            )
            self._audit(
                connection,
                approval_id=approval_id,
                from_state=None if previous is None else previous.state,
                to_state=_REQUESTED,
                reason="/ai_upbit_go accepted after readiness and HALTED checks",
                occurred_at=reference,
            )
            state = self._read(connection)
            assert state is not None
            return state

    def confirm(
        self,
        *,
        approval_id: str,
        operator_id: str,
        now: datetime | None = None,
    ) -> LiveApprovalState:
        reference = self._validate_now(now)
        with self._connect() as connection:
            state = self._read(connection)
            if state is None or state.approval_id != approval_id:
                raise LiveApprovalError("approval sequence not found")
            if state.is_expired(now=reference):
                raise LiveApprovalError("approval sequence expired")
            if state.state != _REQUESTED:
                raise LiveApprovalError("approval must be REQUESTED before confirm")
            if state.operator_fingerprint != self._fingerprint_operator(operator_id):
                raise LiveApprovalError("operator mismatch")
            connection.execute(
                """
                UPDATE crypto_live_approval
                SET state = ?, confirmed_at_utc = ?, updated_at_utc = ?
                WHERE singleton_id = 1
                """,
                (_CONFIRMED, reference.isoformat(), reference.isoformat()),
            )
            self._audit(
                connection,
                approval_id=approval_id,
                from_state=_REQUESTED,
                to_state=_CONFIRMED,
                reason="/confirm accepted",
                occurred_at=reference,
            )
            result = self._read(connection)
            assert result is not None
            return result

    def activate(
        self,
        *,
        approval_id: str,
        operator_id: str,
        readiness_fingerprint: str,
        readiness_passed: bool,
        halted: bool,
        live_environment_enabled: bool,
        now: datetime | None = None,
    ) -> LiveApprovalState:
        reference = self._validate_now(now)
        with self._connect() as connection:
            state = self._read(connection)
            if state is None or state.approval_id != approval_id:
                raise LiveApprovalError("approval sequence not found")
            if state.is_expired(now=reference):
                raise LiveApprovalError("approval sequence expired")
            if state.state != _CONFIRMED:
                raise LiveApprovalError("approval must be CONFIRMED before /go")
            if state.operator_fingerprint != self._fingerprint_operator(operator_id):
                raise LiveApprovalError("operator mismatch")
            if not readiness_passed or readiness_fingerprint != state.readiness_fingerprint:
                raise LiveApprovalError("readiness evidence changed or no longer passes")
            if halted:
                raise LiveApprovalError("HALTED state blocks activation")
            if not live_environment_enabled:
                raise LiveApprovalError("LIVE environment guard is disabled")
            connection.execute(
                """
                UPDATE crypto_live_approval
                SET state = ?, activated_at_utc = ?, updated_at_utc = ?
                WHERE singleton_id = 1
                """,
                (_ACTIVE, reference.isoformat(), reference.isoformat()),
            )
            self._audit(
                connection,
                approval_id=approval_id,
                from_state=_CONFIRMED,
                to_state=_ACTIVE,
                reason="/go accepted; approval state ACTIVE only",
                occurred_at=reference,
            )
            result = self._read(connection)
            assert result is not None
            return result

    def revoke(self, *, reason: str, now: datetime | None = None) -> LiveApprovalState | None:
        reference = self._validate_now(now)
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise ValueError("revoke reason is required")
        with self._connect() as connection:
            state = self._read(connection)
            if state is None:
                return None
            if state.state == _REVOKED:
                return state
            connection.execute(
                "UPDATE crypto_live_approval SET state = ?, updated_at_utc = ? WHERE singleton_id = 1",
                (_REVOKED, reference.isoformat()),
            )
            self._audit(
                connection,
                approval_id=state.approval_id,
                from_state=state.state,
                to_state=_REVOKED,
                reason=normalized_reason,
                occurred_at=reference,
            )
            return self._read(connection)


__all__ = ["LiveApprovalError", "LiveApprovalState", "LiveApprovalStore"]
