from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from decimal import Decimal

from aipro.crypto.account import AccountBalance, AccountOrder, UpbitAccountError
from aipro.crypto.verify_readonly import build_report, run_verification


class FakeClient:
    def __init__(self, *, credentials) -> None:
        self.credentials = credentials

    def balances(self):
        return (
            AccountBalance("BTC", Decimal("0.1"), Decimal("0"), Decimal("100"), "KRW"),
            AccountBalance("KRW", Decimal("100000"), Decimal("0"), Decimal("0"), "KRW"),
        )

    def open_orders(self):
        return (
            AccountOrder(
                uuid="order-1",
                market="KRW-BTC",
                side="bid",
                state="wait",
                order_type="limit",
                price=Decimal("100"),
                volume=Decimal("0.1"),
                remaining_volume=Decimal("0.1"),
                executed_volume=Decimal("0"),
                created_at="2026-07-19T00:00:00+00:00",
            ),
        )


class FailingClient:
    def __init__(self, *, credentials) -> None:
        self.credentials = credentials

    def balances(self):
        raise UpbitAccountError("read-only probe rejected")

    def open_orders(self):
        raise AssertionError("must not continue after balance failure")


def test_build_report_redacts_values_and_is_deterministic() -> None:
    client = FakeClient(credentials=object())
    now = datetime(2026, 7, 19, tzinfo=UTC)

    report = build_report(client.balances(), client.open_orders(), now=now)

    assert report.status == "PASS"
    assert report.balance_asset_count == 2
    assert report.balance_currencies == ("BTC", "KRW")
    assert report.open_order_count == 1
    assert report.open_order_markets == ("KRW-BTC",)
    assert report.mutation_capability == "absent"
    assert len(report.snapshot_fingerprint) == 64
    assert "100000" not in json.dumps(report.__dict__ if hasattr(report, "__dict__") else {})


def test_verification_requires_explicit_supervised_guard() -> None:
    stdout = io.StringIO()
    stderr = io.StringIO()

    exit_code = run_verification(environ={}, stdout=stdout, stderr=stderr, client_factory=FakeClient)

    assert exit_code == 2
    assert stdout.getvalue() == ""
    assert "AIPRO_UPBIT_READONLY_VERIFY=YES" in stderr.getvalue()


def test_verification_outputs_redacted_json() -> None:
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

    payload = json.loads(stdout.getvalue())
    assert exit_code == 0
    assert stderr.getvalue() == ""
    assert payload["status"] == "PASS"
    assert payload["balance_currencies"] == ["BTC", "KRW"]
    assert payload["mutation_capability"] == "absent"
    assert "access-secret" not in stdout.getvalue()
    assert "signing-secret" not in stdout.getvalue()
    assert "100000" not in stdout.getvalue()
    assert "order-1" not in stdout.getvalue()


def test_verification_fails_closed_without_leaking_credentials() -> None:
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
        client_factory=FailingClient,
    )

    assert exit_code == 1
    assert stdout.getvalue() == ""
    assert "read-only probe rejected" in stderr.getvalue()
    assert "access-secret" not in stderr.getvalue()
    assert "signing-secret" not in stderr.getvalue()
