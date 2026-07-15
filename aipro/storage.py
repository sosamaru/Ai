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
            conn.execute("""CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL
            )""")

    def record(self, event_type: str, payload: str) -> None:
        with self._connect() as conn:
            conn.execute("INSERT INTO events(event_type, payload) VALUES (?, ?)", (event_type, payload))
