from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from aipro.sqlite_utils import connect
from aipro.us_stocks.paper_evidence import PaperEvidenceSnapshot, PaperEvidenceStore
from aipro.us_stocks.paper_readiness import (
    AlpacaPaperReadinessMonitor,
    PaperReadinessPolicy,
    PaperReadinessReportStore,
)


def _account(equity: str = "100000", **overrides):
    result = {
        "status": "ACTIVE",
        "equity": equity,
        "trading_blocked": False,
        "account_blocked": False,
        "trade_suspended_by_user": False,
    }
    result.update(overrides)
    return result


def _append(store, when, equity="100000", orders=(), **account_overrides):
    store.append(PaperEvidenceSnapshot(
        captured_at_utc=when.isoformat(),
        account=_account(equity, **account_overrides),
        orders=tuple(orders),
    ))


def test_qualifies_after_contiguous_30_days_and_repeated_snapshot_order_is_not_duplicate(tmp_path):
    evidence_path = tmp_path / "evidence.sqlite3"
    evidence = PaperEvidenceStore(evidence_path)
    start = datetime(2026, 6, 1, 12, tzinfo=UTC)
    order = {"id": "order-1", "client_order_id": "client-1"}
    for offset in range(30):
        _append(evidence, start + timedelta(days=offset), orders=(order,))

    monitor = AlpacaPaperReadinessMonitor(
        evidence_path=evidence_path,
        report_store=PaperReadinessReportStore(tmp_path / "reports.sqlite3"),
    )
    report = monitor.evaluate(evaluated_at_utc=start + timedelta(days=30))

    assert report.qualifying
    assert report.elapsed_calendar_days == 30
    assert report.covered_utc_dates == 30
    assert report.distinct_order_count == 1
    assert report.duplicate_client_order_ids == ()
    assert report.reasons == ()


def test_detects_missing_day_gap_unhealthy_account_duplicate_id_and_drawdown(tmp_path):
    evidence_path = tmp_path / "evidence.sqlite3"
    evidence = PaperEvidenceStore(evidence_path)
    start = datetime(2026, 6, 1, 12, tzinfo=UTC)
    _append(evidence, start, equity="100000", orders=({"id": "a", "client_order_id": "same"},))
    _append(
        evidence,
        start + timedelta(days=2),
        equity="80000",
        orders=({"id": "b", "client_order_id": "same"},),
        trading_blocked=True,
    )

    monitor = AlpacaPaperReadinessMonitor(
        evidence_path=evidence_path,
        report_store=PaperReadinessReportStore(tmp_path / "reports.sqlite3"),
        policy=PaperReadinessPolicy(
            minimum_calendar_days=3,
            maximum_capture_gap_hours=24,
            maximum_drawdown_pct=Decimal("10"),
            minimum_distinct_orders=1,
        ),
    )
    report = monitor.evaluate(evaluated_at_utc=start + timedelta(days=3))

    assert not report.qualifying
    assert report.missing_utc_dates == ("2026-06-02",)
    assert report.duplicate_client_order_ids == ("same",)
    assert report.maximum_drawdown_pct == "20.000000"
    assert set(report.reasons) == {
        "MISSING_DAILY_EVIDENCE",
        "CAPTURE_GAP_EXCEEDED",
        "UNHEALTHY_ACCOUNT_EVIDENCE",
        "DUPLICATE_CLIENT_ORDER_ID",
        "MAXIMUM_DRAWDOWN_EXCEEDED",
    }


def test_empty_evidence_fails_closed_and_report_store_is_append_only(tmp_path):
    evidence_path = tmp_path / "evidence.sqlite3"
    PaperEvidenceStore(evidence_path)
    report_path = tmp_path / "reports.sqlite3"
    monitor = AlpacaPaperReadinessMonitor(
        evidence_path=evidence_path,
        report_store=PaperReadinessReportStore(report_path),
    )
    report = monitor.evaluate(evaluated_at_utc=datetime(2026, 7, 26, tzinfo=UTC))
    assert not report.qualifying
    assert report.reasons == ("NO_EVIDENCE",)

    with connect(report_path) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM paper_readiness_reports")
