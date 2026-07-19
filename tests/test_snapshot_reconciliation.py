from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aipro.crypto.account import AccountBalance, AccountOrder
from aipro.crypto.account_snapshot import ReadOnlyAccountSnapshotStore
from aipro.crypto.snapshot_reconciliation import (
    PaperAccountObservation,
    SnapshotComparisonEvidenceStore,
    compare_snapshot_to_paper,
)


def _snapshot(tmp_path, *, captured_at: datetime):
    store = ReadOnlyAccountSnapshotStore(tmp_path / "exchange.sqlite3")
    return store.append(
        (
            AccountBalance("KRW", Decimal("100000"), Decimal("5000"), Decimal("0"), "KRW"),
            AccountBalance("BTC", Decimal("0.1"), Decimal("0"), Decimal("50000000"), "KRW"),
        ),
        (
            AccountOrder(
                uuid="exchange-order-1",
                market="KRW-BTC",
                side="bid",
                state="wait",
                order_type="limit",
                price=Decimal("50000000"),
                volume=Decimal("0.01"),
                remaining_volume=Decimal("0.01"),
                executed_volume=Decimal("0"),
                created_at=captured_at.isoformat(),
                identifier="client-order-1",
            ),
        ),
        captured_at=captured_at,
    )


def test_matching_observation_creates_match(tmp_path) -> None:
    now = datetime(2026, 7, 19, 2, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path, captured_at=now - timedelta(seconds=10))
    paper = PaperAccountObservation(
        observed_at_utc=now.isoformat(),
        balances={"KRW": Decimal("105000"), "BTC": Decimal("0.1")},
        open_order_ids=("exchange-order-1",),
    )

    result = compare_snapshot_to_paper(snapshot, paper, now=now)

    assert result.status == "MATCH"
    assert result.balance_mismatches == ()
    assert len(result.evidence_fingerprint) == 64


def test_balance_and_order_difference_creates_mismatch(tmp_path) -> None:
    now = datetime(2026, 7, 19, 2, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path, captured_at=now)
    paper = PaperAccountObservation(
        observed_at_utc=now.isoformat(),
        balances={"KRW": Decimal("100000"), "ETH": Decimal("1")},
        open_order_ids=("paper-order-2",),
    )

    result = compare_snapshot_to_paper(snapshot, paper, now=now)

    assert result.status == "MISMATCH"
    assert result.balance_mismatches == ("KRW",)
    assert result.exchange_only_currencies == ("BTC",)
    assert result.paper_only_currencies == ("ETH",)
    assert result.exchange_only_order_ids == ("exchange-order-1",)
    assert result.paper_only_order_ids == ("paper-order-2",)


def test_stale_snapshot_has_priority_over_content_match(tmp_path) -> None:
    now = datetime(2026, 7, 19, 2, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path, captured_at=now - timedelta(minutes=10))
    paper = PaperAccountObservation(
        observed_at_utc=now.isoformat(),
        balances={"KRW": Decimal("105000"), "BTC": Decimal("0.1")},
        open_order_ids=("exchange-order-1",),
    )

    result = compare_snapshot_to_paper(snapshot, paper, now=now, max_snapshot_age_seconds=60)

    assert result.status == "STALE"
    assert result.snapshot_age_seconds == 600.0


def test_evidence_store_is_append_only_and_separate(tmp_path) -> None:
    now = datetime(2026, 7, 19, 2, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path, captured_at=now)
    paper = PaperAccountObservation(
        observed_at_utc=now.isoformat(),
        balances={"KRW": Decimal("105000"), "BTC": Decimal("0.1")},
        open_order_ids=("exchange-order-1",),
    )
    result = compare_snapshot_to_paper(snapshot, paper, now=now)
    database = tmp_path / "evidence.sqlite3"
    store = SnapshotComparisonEvidenceStore(database)

    stored = store.append(result)

    assert stored.status == "MATCH"
    payload = json.loads(stored.payload_json)
    assert payload["snapshot_id"] == snapshot.snapshot_id
    with sqlite3.connect(database) as connection:
        table_names = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }
        assert "exchange_snapshot_comparison_evidence" in table_names
        assert "paper_positions" not in table_names
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "UPDATE exchange_snapshot_comparison_evidence SET status='STALE' WHERE evidence_id=?",
                (stored.evidence_id,),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute(
                "DELETE FROM exchange_snapshot_comparison_evidence WHERE evidence_id=?",
                (stored.evidence_id,),
            )


def test_naive_timestamps_fail_closed(tmp_path) -> None:
    now = datetime(2026, 7, 19, 2, 0, tzinfo=UTC)
    snapshot = _snapshot(tmp_path, captured_at=now)
    paper = PaperAccountObservation(
        observed_at_utc="2026-07-19T02:00:00",
        balances={"KRW": Decimal("105000"), "BTC": Decimal("0.1")},
    )

    with pytest.raises(ValueError, match="timezone-aware"):
        compare_snapshot_to_paper(snapshot, paper, now=now)
