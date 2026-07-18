from __future__ import annotations

import json
import sqlite3
from pathlib import Path


class Storage:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS application_state (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS paper_order_archive (
                    client_order_id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    archived_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def record(self, event_type: str, payload: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(event_type, payload) VALUES (?, ?)",
                (event_type, payload),
            )

    def get_state(self, key: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT value FROM application_state WHERE key = ?",
                (key,),
            ).fetchone()
        return None if row is None else str(row[0])

    def set_state(self, key: str, value: str) -> None:
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO application_state(key, value, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET
                       value = excluded.value,
                       updated_at = CURRENT_TIMESTAMP""",
                (key, value),
            )

    def archive_paper_order(self, client_order_id: str, payload: str) -> None:
        """Insert one immutable order snapshot into the archive.

        Repeating the same archive operation is safe. Reusing an archived order ID
        with different contents raises instead of silently overwriting evidence.
        """
        with self._connect() as conn:
            existing = conn.execute(
                "SELECT payload FROM paper_order_archive WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
            if existing is not None:
                if str(existing[0]) != payload:
                    raise ValueError("archived paper order payload is immutable")
                return
            conn.execute(
                "INSERT INTO paper_order_archive(client_order_id, payload) VALUES (?, ?)",
                (client_order_id, payload),
            )

    def get_archived_paper_order(self, client_order_id: str) -> str | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM paper_order_archive WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
        return None if row is None else str(row[0])

    def list_archived_paper_orders(self) -> tuple[str, ...]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM paper_order_archive ORDER BY archived_at, client_order_id"
            ).fetchall()
        return tuple(str(row[0]) for row in rows)

    def completed_paper_order_ids(self) -> tuple[str, ...]:
        """Return completed order IDs in original event insertion order."""
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT payload FROM events
                   WHERE event_type IN ('paper_order_filled', 'paper_order_no_position')
                   ORDER BY id"""
            ).fetchall()

        ordered: list[str] = []
        seen: set[str] = set()
        for row in rows:
            try:
                payload = json.loads(str(row[0]))
                order_id = str(payload["client_order_id"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                continue
            if order_id not in seen:
                seen.add(order_id)
                ordered.append(order_id)
        return tuple(ordered)
