from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import TextIO

from aipro.crypto.account import (
    AccountBalance,
    AccountOrder,
    UpbitAccountError,
    UpbitCredentials,
    UpbitReadOnlyAccountClient,
)
from aipro.crypto.account_snapshot import ReadOnlyAccountSnapshotStore

_VERIFY_ENV = "AIPRO_UPBIT_READONLY_VERIFY"
_VERIFY_VALUE = "YES"
_SNAPSHOT_DB_ENV = "AIPRO_UPBIT_SNAPSHOT_DB"


@dataclass(frozen=True, slots=True)
class ReadOnlyVerificationReport:
    status: str
    checked_at_utc: str
    balance_asset_count: int
    balance_currencies: tuple[str, ...]
    open_order_count: int
    open_order_markets: tuple[str, ...]
    open_order_states: tuple[str, ...]
    snapshot_fingerprint: str
    permissions_verified: tuple[str, ...]
    snapshot_persisted: bool = False
    snapshot_id: int | None = None
    reconciliation_status: str = "UNCOMPARED"
    mutation_capability: str = "absent"


def _fingerprint(
    balances: Sequence[AccountBalance],
    orders: Sequence[AccountOrder],
) -> str:
    canonical = {
        "balances": [
            {
                "currency": item.currency,
                "unit_currency": item.unit_currency,
                "balance": str(item.balance),
                "locked": str(item.locked),
                "average_buy_price": str(item.average_buy_price),
            }
            for item in sorted(balances, key=lambda value: value.currency)
        ],
        "orders": [
            {
                "uuid": item.uuid,
                "market": item.market,
                "side": item.side,
                "state": item.state,
                "order_type": item.order_type,
                "price": None if item.price is None else str(item.price),
                "volume": None if item.volume is None else str(item.volume),
                "remaining_volume": (
                    None if item.remaining_volume is None else str(item.remaining_volume)
                ),
                "executed_volume": str(item.executed_volume),
                "created_at": item.created_at,
                "identifier": item.identifier,
            }
            for item in sorted(orders, key=lambda value: value.uuid)
        ],
    }
    payload = json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_report(
    balances: Sequence[AccountBalance],
    orders: Sequence[AccountOrder],
    *,
    now: datetime | None = None,
) -> ReadOnlyVerificationReport:
    checked_at = now or datetime.now(UTC)
    if checked_at.tzinfo is None:
        raise ValueError("verification timestamp must be timezone-aware")
    return ReadOnlyVerificationReport(
        status="PASS",
        checked_at_utc=checked_at.astimezone(UTC).isoformat(),
        balance_asset_count=len(balances),
        balance_currencies=tuple(sorted(item.currency for item in balances)),
        open_order_count=len(orders),
        open_order_markets=tuple(sorted({item.market for item in orders})),
        open_order_states=tuple(sorted({item.state for item in orders})),
        snapshot_fingerprint=_fingerprint(balances, orders),
        permissions_verified=("accounts:read", "orders:read"),
    )


def run_verification(
    *,
    environ: Mapping[str, str] | None = None,
    stdout: TextIO = sys.stdout,
    stderr: TextIO = sys.stderr,
    client_factory=UpbitReadOnlyAccountClient,
    snapshot_store_factory=ReadOnlyAccountSnapshotStore,
) -> int:
    env = os.environ if environ is None else environ
    if env.get(_VERIFY_ENV, "").strip().upper() != _VERIFY_VALUE:
        print(
            f"verification blocked: set {_VERIFY_ENV}={_VERIFY_VALUE} for this supervised GET-only probe",
            file=stderr,
        )
        return 2

    try:
        credentials = UpbitCredentials(
            access_key=env.get("AIPRO_UPBIT_ACCESS_KEY", "").strip(),
            secret_key=env.get("AIPRO_UPBIT_SECRET_KEY", "").strip(),
        )
        client = client_factory(credentials=credentials)
        balances = client.balances()
        orders = client.open_orders()
        checked_at = datetime.now(UTC)
        report = build_report(balances, orders, now=checked_at)
        snapshot_db = env.get(_SNAPSHOT_DB_ENV, "").strip()
        if snapshot_db:
            stored = snapshot_store_factory(snapshot_db).append(
                balances,
                orders,
                captured_at=checked_at,
                reconciliation_status="UNCOMPARED",
            )
            report = replace(
                report,
                snapshot_persisted=True,
                snapshot_id=stored.snapshot_id,
                reconciliation_status=stored.reconciliation_status,
            )
    except (ValueError, OSError, UpbitAccountError) as exc:
        print(f"verification failed: {exc}", file=stderr)
        return 1

    print(json.dumps(asdict(report), sort_keys=True, separators=(",", ":")), file=stdout)
    return 0


def main() -> int:
    return run_verification()


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ReadOnlyVerificationReport",
    "build_report",
    "main",
    "run_verification",
]
