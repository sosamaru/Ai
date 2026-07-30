from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from aipro.sqlite_utils import connect


ROOT = Path(__file__).resolve().parents[1]


def test_closing_connection_commits_and_rejects_use_after_context(tmp_path) -> None:
    database = tmp_path / "closing.sqlite3"

    with connect(database) as connection:
        connection.execute("CREATE TABLE sample(value TEXT NOT NULL)")
        connection.execute("INSERT INTO sample(value) VALUES ('saved')")

    with pytest.raises(sqlite3.ProgrammingError, match="closed"):
        connection.execute("SELECT 1")

    with connect(database) as reader:
        assert reader.execute("SELECT value FROM sample").fetchone()[0] == "saved"


def test_application_code_uses_explicitly_closing_sqlite_helper() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "aipro").rglob("*.py")):
        if path.name == "sqlite_utils.py":
            continue
        source = path.read_text(encoding="utf-8")
        if "sqlite3.connect(" in source:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == [], (
        "Application SQLite connections must use aipro.sqlite_utils.connect so "
        f"transaction contexts also close the database. Offenders: {offenders}"
    )
