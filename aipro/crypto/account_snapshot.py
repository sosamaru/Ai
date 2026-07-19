from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from aipro.crypto.account import AccountBalance, AccountOrder

_SCHEMA_VERSION = 1
_RECONCILIATION_STATES = frozenset({"UNCOMPARED", "MATCH", "MISMATCH", "STALE"})


@dataclass(frozen=True, slots=True)
class StoredAccountSnapshot:
    snapshot_id: int
    captured_at_utc: str
    fingerprint: str
    reconciliation_status: str
    payload_json: str

    def age_seconds(self, *, now: datetime | None = None) -> float:
        reference = now or datetime.now(UTC)
        if reference.tzinfo is None:
            raise ValueError("snapshot age reference must be timezone-aware")
        captured = datetime.fromisoformat(self.captured_at_utc)
        if captured.tzinfo is None:
            raise ValueError("stored snapshot timestamp must be timezone-aware")
        return max(0.0, (reference.astimezone(UTC) - captured.astimezone(UTC)).total_seconds())


def canonical_snapshot_payload(
    balances: Sequence[AccountBalance],
    orders: Sequence[AccountOrder],
) -> str:
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "balances": [
            {
                "currency": item.currency,
                "unit_currency": item.unit_currency,
                "balance": str(item.balance),
                "locked": str(item.locked),
                "average_buy_price": str(item.average_buy_price),
            }
            for item in sorted(balances, key=lambda value: (value.unit_currency, value.currency))
        ],
        "open_orders": [
            {
                "uuid": item.uuid,
                "identifier": item.identifier,
                "market": item.market,
                "side": item.side,
                "state": item.state,
                "order_type": item.order_type,
                "price": None if item.price is None else str(item.price),
                "volume": None if item.volume is None else str(item.volume),
                "remaining_volume": (
                    None if item.remaining_volume is None else str(item.remaining_volume)
                ),
                "executed_volume": str(item.executed_volume),
                "created_at": item.created_at,
            }
            for item in sorted(orders, key=lambda value: value.uuid)
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def snapshot_fingerprint(payload_json: str) -> str:
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


class ReadOnlyAccountSnapshotStore:
    """Append-only exchange snapshot storage isolated from PAPER state."""

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
                CREATE TABLE IF NOT EXISTS exchange_account_snapshots (
                    snapshot_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    asset_domain TEXT NOT NULL CHECK(asset_domain = 'crypto'),
                    source TEXT NOT NULL CHECK(source = 'upbit-readonly'),
                    captured_at_utc TEXT NOT NULL,
                    fingerprint TEXT NOT NULL CHECK(length(fingerprint) = 64),
                    reconciliation_status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at_utc TEXT NOT NULL,
                    UNIQUE(captured_at_utc, fingerprint)
                )
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS exchange_account_snapshots_no_update
                BEFORE UPDATE ON exchange_account_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'exchange snapshots are immutable');
                END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS exchange_account_snapshots_no_delete
                BEFORE DELETE ON exchange_account_snapshots
                BEGIN
                    SELECT RAISE(ABORT, 'exchange snapshots are immutable');
                END
                """
            )

    def append(
        self,
        balances: Sequence[AccountBalance],
        orders: Sequence[AccountOrder],
        *,
        captured_at: datetime | None = None,
        reconciliation_status: str = "UNCOMPARED",
    ) -> StoredAccountSnapshot:
        status = reconciliation_status.strip().upper()
        if status not in _RECONCILIATION_STATES:
            raise ValueError(f"invalid reconciliation status: {reconciliation_status}")
        timestamp = captured_at or datetime.now(UTC)
        if timestamp.tzinfo is None:
            raise ValueError("snapshot timestamp must be timezone-aware")
        captured_at_utc = timestamp.astimezone(UTC).isoformat()
        payload_json = canonical_snapshot_payload(balances, orders)
        fingerprint = snapshot_fingerprint(payload_json)
        created_at_utc = datetime.now(UTC).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO exchange_account_snapshots (
                    asset_domain, source, captured_at_utc, fingerprint,
                    reconciliation_status, payload_json, created_at_utc
                ) VALUES ('crypto', 'upbit-readonly', ?, ?, ?, ?, ?)
                """,
                (captured_at_utc, fingerprint, status, payload_json, created_at_utc),
            )
            snapshot_id = int(cursor.lastrowid)
        return StoredAccountSnapshot(
            snapshot_id=snapshot_id,
            captured_at_utc=captured_at_utc,
            fingerprint=fingerprint,
            reconciliation_status=status,
            payload_json=payload_json,
        )

    def latest(self) -> StoredAccountSnapshot | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT snapshot_id, captured_at_utc, fingerprint,
                       reconciliation_status, payload_json
                FROM exchange_account_snapshots
                ORDER BY snapshot_id DESC
                LIMIT 1
                """
            ).fetchone()
        if row is None:
            return None
        return StoredAccountSnapshot(
            snapshot_id=int(row["snapshot_id"]),
            captured_at_utc=str(row["captured_at_utc"]),
            fingerprint=str(row["fingerprint"]),
            reconciliation_status=str(row["reconciliation_status"]),
            payload_json=str(row["payload_json"]),
        )


__all__ = [
    "ReadOnlyAccountSnapshotStore",
    "StoredAccountSnapshot",
    "canonical_snapshot_payload",
    "snapshot_fingerprint",
]
