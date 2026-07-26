from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True, slots=True)
class PaperReadinessPolicy:
    minimum_calendar_days: int = 30
    maximum_capture_gap_hours: int = 36
    maximum_drawdown_pct: Decimal = Decimal("10")
    minimum_distinct_orders: int = 1

    def __post_init__(self) -> None:
        if self.minimum_calendar_days < 1:
            raise ValueError("minimum_calendar_days must be positive")
        if self.maximum_capture_gap_hours < 1:
            raise ValueError("maximum_capture_gap_hours must be positive")
        if not Decimal("0") <= self.maximum_drawdown_pct <= Decimal("100"):
            raise ValueError("maximum_drawdown_pct must be between 0 and 100")
        if self.minimum_distinct_orders < 0:
            raise ValueError("minimum_distinct_orders cannot be negative")


@dataclass(frozen=True, slots=True)
class PaperReadinessReport:
    evaluated_at_utc: str
    first_capture_utc: str | None
    last_capture_utc: str | None
    elapsed_calendar_days: int
    covered_utc_dates: int
    missing_utc_dates: tuple[str, ...]
    maximum_capture_gap_hours: str
    distinct_order_count: int
    duplicate_client_order_ids: tuple[str, ...]
    unhealthy_capture_count: int
    peak_equity: str
    latest_equity: str
    maximum_drawdown_pct: str
    qualifying: bool
    reasons: tuple[str, ...]

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class PaperReadinessReportStore:
    """Append-only store for derived readiness decisions.

    The report is evidence about PAPER operation only. It grants no execution
    authority and does not modify account, order, authorization, or risk state.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS paper_readiness_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluated_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS paper_readiness_reports_no_update
                BEFORE UPDATE ON paper_readiness_reports
                BEGIN SELECT RAISE(ABORT, 'append only'); END;
                CREATE TRIGGER IF NOT EXISTS paper_readiness_reports_no_delete
                BEFORE DELETE ON paper_readiness_reports
                BEGIN SELECT RAISE(ABORT, 'append only'); END;
                """
            )

    def append(self, report: PaperReadinessReport) -> str:
        parsed = datetime.fromisoformat(report.evaluated_at_utc)
        if parsed.tzinfo is None:
            raise ValueError("evaluated_at_utc must be timezone-aware")
        payload = json.dumps(asdict(report), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT INTO paper_readiness_reports(evaluated_at_utc,payload_json,fingerprint) VALUES(?,?,?)",
                (report.evaluated_at_utc, payload, report.fingerprint),
            )
        return report.fingerprint


def _decimal(value: Any, *, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid {field}")
    return result


def _load_snapshots(path: str | Path) -> tuple[dict[str, Any], ...]:
    with sqlite3.connect(str(path)) as db:
        rows = db.execute(
            "SELECT payload_json FROM paper_evidence ORDER BY captured_at_utc ASC, id ASC"
        ).fetchall()
    snapshots: list[dict[str, Any]] = []
    for (payload_json,) in rows:
        payload = json.loads(payload_json)
        if not isinstance(payload, dict):
            raise ValueError("invalid PAPER evidence payload")
        snapshots.append(payload)
    return tuple(snapshots)


def _is_account_healthy(account: dict[str, Any]) -> bool:
    status = str(account.get("status", "")).upper()
    return (
        status == "ACTIVE"
        and not bool(account.get("trading_blocked", False))
        and not bool(account.get("account_blocked", False))
        and not bool(account.get("trade_suspended_by_user", False))
    )


def _utc_dates_between(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


class AlpacaPaperReadinessMonitor:
    def __init__(
        self,
        *,
        evidence_path: str | Path,
        report_store: PaperReadinessReportStore,
        policy: PaperReadinessPolicy | None = None,
    ) -> None:
        self.evidence_path = str(evidence_path)
        self.report_store = report_store
        self.policy = policy or PaperReadinessPolicy()

    def evaluate(self, *, evaluated_at_utc: datetime) -> PaperReadinessReport:
        if evaluated_at_utc.tzinfo is None:
            raise ValueError("evaluated_at_utc must be timezone-aware")
        now = evaluated_at_utc.astimezone(UTC)
        snapshots = _load_snapshots(self.evidence_path)
        reasons: list[str] = []

        if not snapshots:
            report = PaperReadinessReport(
                evaluated_at_utc=now.isoformat(),
                first_capture_utc=None,
                last_capture_utc=None,
                elapsed_calendar_days=0,
                covered_utc_dates=0,
                missing_utc_dates=(),
                maximum_capture_gap_hours="0",
                distinct_order_count=0,
                duplicate_client_order_ids=(),
                unhealthy_capture_count=0,
                peak_equity="0",
                latest_equity="0",
                maximum_drawdown_pct="0",
                qualifying=False,
                reasons=("NO_EVIDENCE",),
            )
            self.report_store.append(report)
            return report

        captured: list[datetime] = []
        equities: list[Decimal] = []
        unhealthy = 0
        client_order_counts: dict[str, int] = {}
        order_ids: set[str] = set()

        for snapshot in snapshots:
            captured_at = datetime.fromisoformat(str(snapshot.get("captured_at_utc", "")))
            if captured_at.tzinfo is None:
                raise ValueError("PAPER evidence timestamp must be timezone-aware")
            captured.append(captured_at.astimezone(UTC))

            account = snapshot.get("account")
            if not isinstance(account, dict):
                raise ValueError("invalid PAPER account evidence")
            if not _is_account_healthy(account):
                unhealthy += 1
            equities.append(_decimal(account.get("equity"), field="account equity"))

            orders = snapshot.get("orders", ())
            if not isinstance(orders, (list, tuple)):
                raise ValueError("invalid PAPER order evidence")
            for order in orders:
                if not isinstance(order, dict):
                    continue
                order_id = str(order.get("id", "")).strip()
                if order_id:
                    order_ids.add(order_id)
                client_id = str(order.get("client_order_id", "")).strip()
                if client_id:
                    client_order_counts[client_id] = client_order_counts.get(client_id, 0) + 1

        first = captured[0]
        last = captured[-1]
        if last > now:
            reasons.append("FUTURE_EVIDENCE")
        elapsed_days = (last.date() - first.date()).days + 1
        covered_dates = {item.date() for item in captured}
        missing_dates = tuple(
            item.isoformat()
            for item in _utc_dates_between(first.date(), last.date())
            if item not in covered_dates
        )

        gaps = [
            (right - left).total_seconds() / 3600
            for left, right in zip(captured, captured[1:])
        ]
        maximum_gap = max(gaps, default=0.0)

        peak = equities[0]
        maximum_drawdown = Decimal("0")
        for equity in equities:
            if equity > peak:
                peak = equity
            if peak > 0:
                drawdown = (peak - equity) / peak * Decimal("100")
                if drawdown > maximum_drawdown:
                    maximum_drawdown = drawdown

        duplicates = tuple(sorted(key for key, count in client_order_counts.items() if count > 1))

        if elapsed_days < self.policy.minimum_calendar_days:
            reasons.append("MINIMUM_CALENDAR_DAYS_NOT_MET")
        if missing_dates:
            reasons.append("MISSING_DAILY_EVIDENCE")
        if maximum_gap > self.policy.maximum_capture_gap_hours:
            reasons.append("CAPTURE_GAP_EXCEEDED")
        if unhealthy:
            reasons.append("UNHEALTHY_ACCOUNT_EVIDENCE")
        if duplicates:
            reasons.append("DUPLICATE_CLIENT_ORDER_ID")
        if len(order_ids) < self.policy.minimum_distinct_orders:
            reasons.append("MINIMUM_DISTINCT_ORDERS_NOT_MET")
        if maximum_drawdown > self.policy.maximum_drawdown_pct:
            reasons.append("MAXIMUM_DRAWDOWN_EXCEEDED")

        report = PaperReadinessReport(
            evaluated_at_utc=now.isoformat(),
            first_capture_utc=first.isoformat(),
            last_capture_utc=last.isoformat(),
            elapsed_calendar_days=elapsed_days,
            covered_utc_dates=len(covered_dates),
            missing_utc_dates=missing_dates,
            maximum_capture_gap_hours=f"{maximum_gap:.6f}",
            distinct_order_count=len(order_ids),
            duplicate_client_order_ids=duplicates,
            unhealthy_capture_count=unhealthy,
            peak_equity=str(peak),
            latest_equity=str(equities[-1]),
            maximum_drawdown_pct=str(maximum_drawdown.quantize(Decimal('0.000001'))),
            qualifying=not reasons,
            reasons=tuple(reasons),
        )
        self.report_store.append(report)
        return report


__all__ = [
    "AlpacaPaperReadinessMonitor",
    "PaperReadinessPolicy",
    "PaperReadinessReport",
    "PaperReadinessReportStore",
]
