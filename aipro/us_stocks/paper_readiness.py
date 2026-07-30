from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable

from aipro.sqlite_utils import connect


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
        raw = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode()).hexdigest()


class PaperReadinessReportStore:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS paper_readiness_reports(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    evaluated_at_utc TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS paper_readiness_reports_no_update
                BEFORE UPDATE ON paper_readiness_reports BEGIN SELECT RAISE(ABORT,'append only'); END;
                CREATE TRIGGER IF NOT EXISTS paper_readiness_reports_no_delete
                BEFORE DELETE ON paper_readiness_reports BEGIN SELECT RAISE(ABORT,'append only'); END;
            """)

    def append(self, report: PaperReadinessReport) -> str:
        timestamp = datetime.fromisoformat(report.evaluated_at_utc)
        if timestamp.tzinfo is None:
            raise ValueError("evaluated_at_utc must be timezone-aware")
        payload = json.dumps(asdict(report), sort_keys=True, separators=(",", ":"))
        with connect(self.path, timeout=5.0) as db:
            db.execute("PRAGMA busy_timeout = 5000")
            db.execute(
                "INSERT INTO paper_readiness_reports(evaluated_at_utc,payload_json,fingerprint) VALUES(?,?,?)",
                (report.evaluated_at_utc, payload, report.fingerprint),
            )
        return report.fingerprint


def _decimal(value: Any, field: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"invalid {field}") from exc
    if not result.is_finite():
        raise ValueError(f"invalid {field}")
    return result


def _load_snapshots(path: str | Path) -> tuple[dict[str, Any], ...]:
    with connect(str(path), timeout=5.0) as db:
        db.execute("PRAGMA busy_timeout = 5000")
        rows = db.execute(
            "SELECT payload_json FROM paper_evidence ORDER BY captured_at_utc,id"
        ).fetchall()
    result = []
    for (raw,) in rows:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("invalid PAPER evidence payload")
        result.append(payload)
    return tuple(result)


def _dates(start: date, end: date) -> Iterable[date]:
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def _healthy(account: dict[str, Any]) -> bool:
    return (
        str(account.get("status", "")).upper() == "ACTIVE"
        and not bool(account.get("trading_blocked", False))
        and not bool(account.get("account_blocked", False))
        and not bool(account.get("trade_suspended_by_user", False))
    )


class AlpacaPaperReadinessMonitor:
    def __init__(self, *, evidence_path: str | Path, report_store: PaperReadinessReportStore,
                 policy: PaperReadinessPolicy | None = None) -> None:
        self.evidence_path = str(evidence_path)
        self.report_store = report_store
        self.policy = policy or PaperReadinessPolicy()

    def evaluate(self, *, evaluated_at_utc: datetime) -> PaperReadinessReport:
        if evaluated_at_utc.tzinfo is None:
            raise ValueError("evaluated_at_utc must be timezone-aware")
        now = evaluated_at_utc.astimezone(UTC)
        snapshots = _load_snapshots(self.evidence_path)
        if not snapshots:
            report = PaperReadinessReport(now.isoformat(), None, None, 0, 0, (), "0", 0, (), 0,
                                          "0", "0", "0", False, ("NO_EVIDENCE",))
            self.report_store.append(report)
            return report

        captures: list[datetime] = []
        equities: list[Decimal] = []
        unhealthy = 0
        order_ids: set[str] = set()
        client_to_order_ids: dict[str, set[str]] = {}

        for snapshot in snapshots:
            captured = datetime.fromisoformat(str(snapshot.get("captured_at_utc", "")))
            if captured.tzinfo is None:
                raise ValueError("PAPER evidence timestamp must be timezone-aware")
            captures.append(captured.astimezone(UTC))
            account = snapshot.get("account")
            if not isinstance(account, dict):
                raise ValueError("invalid PAPER account evidence")
            unhealthy += int(not _healthy(account))
            equities.append(_decimal(account.get("equity"), "account equity"))
            orders = snapshot.get("orders", ())
            if not isinstance(orders, (list, tuple)):
                raise ValueError("invalid PAPER order evidence")
            for order in orders:
                if not isinstance(order, dict):
                    continue
                order_id = str(order.get("id", "")).strip()
                client_id = str(order.get("client_order_id", "")).strip()
                if order_id:
                    order_ids.add(order_id)
                if order_id and client_id:
                    client_to_order_ids.setdefault(client_id, set()).add(order_id)

        first, last = captures[0], captures[-1]
        covered = {item.date() for item in captures}
        missing = tuple(item.isoformat() for item in _dates(first.date(), last.date()) if item not in covered)
        gaps = [(right - left).total_seconds() / 3600 for left, right in zip(captures, captures[1:])]
        maximum_gap = max(gaps, default=0.0)
        peak = equities[0]
        maximum_drawdown = Decimal("0")
        for equity in equities:
            peak = max(peak, equity)
            if peak > 0:
                maximum_drawdown = max(maximum_drawdown, (peak - equity) / peak * Decimal("100"))
        duplicates = tuple(sorted(key for key, values in client_to_order_ids.items() if len(values) > 1))
        elapsed = (last.date() - first.date()).days + 1

        reasons: list[str] = []
        if last > now:
            reasons.append("FUTURE_EVIDENCE")
        if elapsed < self.policy.minimum_calendar_days:
            reasons.append("MINIMUM_CALENDAR_DAYS_NOT_MET")
        if missing:
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
            now.isoformat(), first.isoformat(), last.isoformat(), elapsed, len(covered), missing,
            f"{maximum_gap:.6f}", len(order_ids), duplicates, unhealthy, str(peak), str(equities[-1]),
            str(maximum_drawdown.quantize(Decimal("0.000001"))), not reasons, tuple(reasons),
        )
        self.report_store.append(report)
        return report


__all__ = ["AlpacaPaperReadinessMonitor", "PaperReadinessPolicy", "PaperReadinessReport", "PaperReadinessReportStore"]
