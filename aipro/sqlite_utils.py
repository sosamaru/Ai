"""SQLite helpers with explicit connection lifetime management."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


class ClosingConnection(sqlite3.Connection):
    """Commit or roll back like sqlite3.Connection, then always close."""

    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def connect(
    database: str | Path,
    *args: Any,
    **kwargs: Any,
) -> ClosingConnection:
    """Return a connection whose context manager also closes the database."""

    kwargs.setdefault("factory", ClosingConnection)
    return sqlite3.connect(database, *args, **kwargs)


__all__ = ["ClosingConnection", "connect"]
