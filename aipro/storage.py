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
        return sqlite3.connect(self.path)

    def _initialize(self) -> None:
        with self._connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL
            )""")
            conn.execute("""CREATE TABLE IF NOT EXISTS state (
                key TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )""")

    def record(self, event_type: str, payload: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO events(event_type, payload) VALUES (?, ?)", (event_type, payload))

    def save_state(self, key: str, value: dict[str, Any]) -> None:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        with self._connect() as conn:
            conn.execute(
                """INSERT INTO state(key, payload, updated_at)
                   VALUES (?, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(key) DO UPDATE SET
                     payload=excluded.payload,
                     updated_at=CURRENT_TIMESTAMP""",
                (key, payload),
            )

    def load_state(self, key: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT payload FROM state WHERE key = ?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def count_events(self, event_type: str | None = None) -> int:
        with self._connect() as conn:
            if event_type is None:
                row = conn.execute("SELECT COUNT(*) FROM events").fetchone()
            else:
                row = conn.execute(
                    "SELECT COUNT(*) FROM events WHERE event_type = ?", (event_type,)
                ).fetchone()
        return int(row[0])
