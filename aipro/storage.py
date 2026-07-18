from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Mapping


class Storage:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        return conn

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
                """CREATE TABLE IF NOT EXISTS paper_account (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    cash_krw REAL NOT NULL CHECK (cash_krw >= 0),
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS paper_positions (
                    symbol TEXT PRIMARY KEY,
                    quantity REAL NOT NULL CHECK (quantity > 0),
                    average_price REAL NOT NULL CHECK (average_price > 0),
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS paper_transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL CHECK (quantity > 0),
                    price REAL NOT NULL CHECK (price > 0),
                    gross_krw REAL NOT NULL CHECK (gross_krw > 0),
                    cash_after_krw REAL NOT NULL CHECK (cash_after_krw >= 0),
                    metadata TEXT NOT NULL DEFAULT '{}'
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

    def load_paper_account(self) -> tuple[float, dict[str, tuple[float, float]]] | None:
        with self._connect() as conn:
            account = conn.execute(
                "SELECT cash_krw FROM paper_account WHERE id = 1"
            ).fetchone()
            if account is None:
                return None
            rows = conn.execute(
                "SELECT symbol, quantity, average_price FROM paper_positions ORDER BY symbol"
            ).fetchall()

        cash_krw = float(account["cash_krw"])
        positions = {
            str(row["symbol"]): (float(row["quantity"]), float(row["average_price"]))
            for row in rows
        }
        if cash_krw < 0 or any(quantity <= 0 or average_price <= 0 for quantity, average_price in positions.values()):
            raise ValueError("corrupted paper account state")
        return cash_krw, positions

    def save_paper_account(
        self,
        cash_krw: float,
        positions: Mapping[str, tuple[float, float]],
        transaction: Mapping[str, object] | None = None,
    ) -> None:
        if cash_krw < 0:
            raise ValueError("cash_krw must be non-negative")
        for symbol, (quantity, average_price) in positions.items():
            if not symbol or quantity <= 0 or average_price <= 0:
                raise ValueError("invalid paper position")

        with self._connect() as conn:
            conn.execute(
                """INSERT INTO paper_account(id, cash_krw, updated_at)
                   VALUES (1, ?, CURRENT_TIMESTAMP)
                   ON CONFLICT(id) DO UPDATE SET
                       cash_krw = excluded.cash_krw,
                       updated_at = CURRENT_TIMESTAMP""",
                (cash_krw,),
            )
            conn.execute("DELETE FROM paper_positions")
            conn.executemany(
                """INSERT INTO paper_positions(symbol, quantity, average_price, updated_at)
                   VALUES (?, ?, ?, CURRENT_TIMESTAMP)""",
                [
                    (symbol, quantity, average_price)
                    for symbol, (quantity, average_price) in sorted(positions.items())
                ],
            )
            if transaction is not None:
                conn.execute(
                    """INSERT INTO paper_transactions(
                           side, symbol, quantity, price, gross_krw, cash_after_krw, metadata
                       ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(transaction["side"]),
                        str(transaction["symbol"]),
                        float(transaction["quantity"]),
                        float(transaction["price"]),
                        float(transaction["gross_krw"]),
                        cash_krw,
                        json.dumps(transaction.get("metadata", {}), sort_keys=True),
                    ),
                )

    def list_paper_transactions(self) -> list[dict[str, object]]:
        with self._connect() as conn:
            rows = conn.execute(
                """SELECT side, symbol, quantity, price, gross_krw, cash_after_krw, metadata
                   FROM paper_transactions ORDER BY id"""
            ).fetchall()
        return [
            {
                "side": str(row["side"]),
                "symbol": str(row["symbol"]),
                "quantity": float(row["quantity"]),
                "price": float(row["price"]),
                "gross_krw": float(row["gross_krw"]),
                "cash_after_krw": float(row["cash_after_krw"]),
                "metadata": json.loads(str(row["metadata"])),
            }
            for row in rows
        ]
