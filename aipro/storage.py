from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class Storage:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

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
                """CREATE TABLE IF NOT EXISTS runtime_state (
                    state_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )

    def record(self, event_type: str, payload: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO events(event_type, payload) VALUES (?, ?)",
                (event_type, payload),
            )

    def save_state(self, state_key: str, payload: dict[str, Any]) -> None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO runtime_state(state_key, payload, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(state_key) DO UPDATE SET
                       payload = excluded.payload,
                       updated_at = CURRENT_TIMESTAMP""",
                (state_key, serialized),
            )

    def load_state(self, state_key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT payload FROM runtime_state WHERE state_key = ?",
                (state_key,),
            ).fetchone()
        if row is None:
            return None
        payload = json.loads(str(row["payload"]))
        if not isinstance(payload, dict):
            raise ValueError("stored runtime state must be a JSON object")
        return payload
