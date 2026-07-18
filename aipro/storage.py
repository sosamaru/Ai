from __future__ import annotations

import sqlite3
from pathlib import Path

from aipro.orders import Order, OrderSide, OrderStatus, require_transition


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
                """CREATE TABLE IF NOT EXISTS orders (
                    client_order_id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    status TEXT NOT NULL,
                    amount_krw INTEGER,
                    quantity REAL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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

    def create_order(self, order: Order) -> bool:
        """Atomically claim a client order ID. Duplicate IDs return False."""
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT INTO orders(
                           client_order_id, symbol, side, status, amount_krw, quantity
                       ) VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        order.client_order_id,
                        order.symbol,
                        order.side.value,
                        order.status.value,
                        order.amount_krw,
                        order.quantity,
                    ),
                )
        except sqlite3.IntegrityError:
            return False
        return True

    def get_order(self, client_order_id: str) -> Order | None:
        with self._connect() as conn:
            row = conn.execute(
                """SELECT client_order_id, symbol, side, status, amount_krw, quantity
                   FROM orders WHERE client_order_id = ?""",
                (client_order_id,),
            ).fetchone()
        if row is None:
            return None
        return Order(
            client_order_id=str(row[0]),
            symbol=str(row[1]),
            side=OrderSide(str(row[2])),
            status=OrderStatus(str(row[3])),
            amount_krw=None if row[4] is None else int(row[4]),
            quantity=None if row[5] is None else float(row[5]),
        )

    def transition_order(self, client_order_id: str, target: OrderStatus) -> Order:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT status FROM orders WHERE client_order_id = ?",
                (client_order_id,),
            ).fetchone()
            if row is None:
                raise KeyError(f"unknown client_order_id: {client_order_id}")
            current = OrderStatus(str(row[0]))
            require_transition(current, target)
            conn.execute(
                """UPDATE orders
                   SET status = ?, updated_at = CURRENT_TIMESTAMP
                   WHERE client_order_id = ? AND status = ?""",
                (target.value, client_order_id, current.value),
            )
        order = self.get_order(client_order_id)
        if order is None:
            raise RuntimeError("order disappeared after transition")
        return order
