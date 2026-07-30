from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from aipro.crypto.account import AccountBalance
from aipro.crypto.account_snapshot import ReadOnlyAccountSnapshotStore
from aipro.crypto.run_snapshot_comparison import run


def _balance(currency: str, amount: str) -> AccountBalance:
    return AccountBalance(
        currency=currency,
        balance=Decimal(amount),
        locked=Decimal("0"),
        average_buy_price=Decimal("0"),
        unit_currency="KRW",
    )


def test_guard_is_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("AIPRO_UPBIT_SNAPSHOT_COMPARE", raising=False)
    with pytest.raises(RuntimeError, match="explicit guard required"):
        run()


def test_runner_compares_latest_snapshot_and_persists_evidence(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_db = tmp_path / "snapshots.sqlite3"
    evidence_db = tmp_path / "evidence.sqlite3"
    paper_json = tmp_path / "paper.json"
    captured_at = datetime.now(UTC)
    snapshot = ReadOnlyAccountSnapshotStore(snapshot_db).append(
        [_balance("KRW", "10000"), _balance("BTC", "0.01")],
        [],
        captured_at=captured_at,
    )
    paper_json.write_text(
        json.dumps(
            {
                "observed_at_utc": captured_at.isoformat(),
                "balances": {"KRW": "10000", "BTC": "0.01"},
                "open_order_ids": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPRO_UPBIT_SNAPSHOT_COMPARE", "YES")
    monkeypatch.setenv("AIPRO_UPBIT_SNAPSHOT_DB", str(snapshot_db))
    monkeypatch.setenv("AIPRO_PAPER_OBSERVATION_JSON", str(paper_json))
    monkeypatch.setenv("AIPRO_UPBIT_COMPARISON_DB", str(evidence_db))
    monkeypatch.setenv("AIPRO_UPBIT_SNAPSHOT_MAX_AGE_SEC", "300")

    report = run()

    assert report["status"] == "MATCH"
    assert report["snapshot_id"] == snapshot.snapshot_id
    assert report["evidence_id"] == 1
    assert len(str(report["evidence_fingerprint"])) == 64


def test_runner_rejects_naive_paper_timestamp(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot_db = tmp_path / "snapshots.sqlite3"
    ReadOnlyAccountSnapshotStore(snapshot_db).append(
        [_balance("KRW", "10000")], [], captured_at=datetime.now(UTC)
    )
    paper_json = tmp_path / "paper.json"
    paper_json.write_text(
        json.dumps(
            {
                "observed_at_utc": "2026-07-19T12:00:00",
                "balances": {"KRW": "10000"},
                "open_order_ids": [],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AIPRO_UPBIT_SNAPSHOT_COMPARE", "YES")
    monkeypatch.setenv("AIPRO_UPBIT_SNAPSHOT_DB", str(snapshot_db))
    monkeypatch.setenv("AIPRO_PAPER_OBSERVATION_JSON", str(paper_json))
    monkeypatch.setenv("AIPRO_UPBIT_COMPARISON_DB", str(tmp_path / "evidence.sqlite3"))

    with pytest.raises(RuntimeError, match="timezone-aware"):
        run()
