from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aipro.crypto.account import AccountBalance, AccountOrder
from aipro.crypto.account_snapshot import ReadOnlyAccountSnapshotStore


def _balances() -> tuple[AccountBalance, ...]:
    return (
        AccountBalance("KRW", Decimal("100000"), Decimal("0"), Decimal("0"), "KRW"),
        AccountBalance("BTC", Decimal("0.1"), Decimal("0.01"), Decimal("90000000"), "KRW"),
    )


def _orders() -> tuple[AccountOrder, ...]:
    return (
        AccountOrder(
            uuid="exchange-order-1",
            market="KRW-BTC",
            side="bid",
            state="wait",
            order_type="limit",
            price=Decimal("85000000"),
            volume=Decimal("0.01"),
            remaining_volume=Decimal("0.01"),
            executed_volume=Decimal("0"),
            created_at="2026-07-19T01:00:00+00:00",
            identifier="readonly-identifier",
        ),
    )


def test_snapshot_store_appends_and_loads_latest(tmp_path) -> None:
    store = ReadOnlyAccountSnapshotStore(tmp_path / "exchange" / "snapshots.sqlite3")
    captured = datetime(2026, 7, 19, 1, 30, tzinfo=UTC)

    stored = store.append(_balances(), _orders(), captured_at=captured)
    latest = store.latest()

    assert latest == stored
    assert stored.snapshot_id == 1
    assert stored.reconciliation_status == "UNCOMPARED"
    assert len(stored.fingerprint) == 64
    payload = json.loads(stored.payload_json)
    assert payload["schema_version"] == 1
    assert payload["balances"][0]["currency"] == "BTC"
    assert payload["open_orders"][0]["uuid"] == "exchange-order-1"
    assert stored.age_seconds(now=captured + timedelta(seconds=45)) == 45.0


def test_snapshot_store_is_append_only(tmp_path) -> None:
    database = tmp_path / "snapshots.sqlite3"
    store = ReadOnlyAccountSnapshotStore(database)
    store.append(_balances(), _orders(), captured_at=datetime(2026, 7, 19, tzinfo=UTC))

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE exchange_account_snapshots SET reconciliation_status = 'MATCH' WHERE snapshot_id = 1"
            )

    with sqlite3.connect(database) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM exchange_account_snapshots WHERE snapshot_id = 1")


def test_snapshot_store_rejects_invalid_metadata(tmp_path) -> None:
    store = ReadOnlyAccountSnapshotStore(tmp_path / "snapshots.sqlite3")

    with pytest.raises(ValueError, match="timezone-aware"):
        store.append(_balances(), _orders(), captured_at=datetime(2026, 7, 19))

    with pytest.raises(ValueError, match="invalid reconciliation status"):
        store.append(_balances(), _orders(), reconciliation_status="UNKNOWN")


def test_snapshot_store_keeps_exchange_namespace_separate(tmp_path) -> None:
    database = tmp_path / "snapshots.sqlite3"
    store = ReadOnlyAccountSnapshotStore(database)
    store.append(_balances(), _orders())

    with sqlite3.connect(database) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        row = connection.execute(
            "SELECT asset_domain, source FROM exchange_account_snapshots"
        ).fetchone()

    assert "exchange_account_snapshots" in tables
    assert row == ("crypto", "upbit-readonly")
    assert not any("paper" in table.lower() for table in tables)
