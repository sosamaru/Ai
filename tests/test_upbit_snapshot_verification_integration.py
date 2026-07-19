from __future__ import annotations

import io
import json
from decimal import Decimal

from aipro.crypto.account import AccountBalance, AccountOrder
from aipro.crypto.account_snapshot import ReadOnlyAccountSnapshotStore
from aipro.crypto.verify_readonly import run_verification


class FakeClient:
    def __init__(self, *, credentials) -> None:
        self.credentials = credentials

    def balances(self):
        return (
            AccountBalance("KRW", Decimal("50000"), Decimal("0"), Decimal("0"), "KRW"),
        )

    def open_orders(self):
        return (
            AccountOrder(
                uuid="private-order-id",
                market="KRW-ETH",
                side="bid",
                state="wait",
                order_type="limit",
                price=Decimal("3000000"),
                volume=Decimal("0.01"),
                remaining_volume=Decimal("0.01"),
                executed_volume=Decimal("0"),
                created_at="2026-07-19T02:00:00+00:00",
            ),
        )


def test_verification_optionally_persists_without_leaking_values(tmp_path) -> None:
    database = tmp_path / "readonly" / "snapshots.sqlite3"
    stdout = io.StringIO()
    stderr = io.StringIO()
    env = {
        "AIPRO_UPBIT_READONLY_VERIFY": "YES",
        "AIPRO_UPBIT_ACCESS_KEY": "access-secret",
        "AIPRO_UPBIT_SECRET_KEY": "signing-secret",
        "AIPRO_UPBIT_SNAPSHOT_DB": str(database),
    }

    exit_code = run_verification(
        environ=env,
        stdout=stdout,
        stderr=stderr,
        client_factory=FakeClient,
    )

    output = stdout.getvalue()
    report = json.loads(output)
    latest = ReadOnlyAccountSnapshotStore(database).latest()
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert report["snapshot_persisted"] is True
    assert report["snapshot_id"] == 1
    assert report["reconciliation_status"] == "UNCOMPARED"
    assert latest is not None
    assert latest.snapshot_id == 1
    assert "50000" not in output
    assert "private-order-id" not in output
    assert "access-secret" not in output
    assert "signing-secret" not in output


def test_verification_does_not_create_snapshot_without_path(tmp_path) -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()
    env = {
        "AIPRO_UPBIT_READONLY_VERIFY": "YES",
        "AIPRO_UPBIT_ACCESS_KEY": "access-secret",
        "AIPRO_UPBIT_SECRET_KEY": "signing-secret",
    }

    exit_code = run_verification(
        environ=env,
        stdout=stdout,
        stderr=stderr,
        client_factory=FakeClient,
    )

    report = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert report["snapshot_persisted"] is False
    assert report["snapshot_id"] is None
    assert list(tmp_path.iterdir()) == []
