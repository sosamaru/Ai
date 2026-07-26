from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from decimal import Decimal

from aipro.us_stocks.alpaca_paper import AlpacaPaperClient
from aipro.us_stocks.paper_evidence import AlpacaPaperEvidenceCollector, PaperEvidenceStore
from aipro.us_stocks.paper_readiness import (
    AlpacaPaperReadinessMonitor,
    PaperReadinessPolicy,
    PaperReadinessReportStore,
)


def main() -> int:
    if os.environ.get("AIPRO_ALPACA_PAPER_VERIFY") != "YES":
        raise SystemExit("AIPRO_ALPACA_PAPER_VERIFY=YES is required")

    evidence_path = os.environ.get("AIPRO_ALPACA_PAPER_EVIDENCE_DB", "data/alpaca_paper_evidence.sqlite3")
    report_path = os.environ.get("AIPRO_ALPACA_PAPER_REPORT_DB", "data/alpaca_paper_readiness.sqlite3")
    now = datetime.now(UTC)

    client = AlpacaPaperClient.from_env()
    collector = AlpacaPaperEvidenceCollector(client, PaperEvidenceStore(evidence_path))
    collector.collect(captured_at_utc=now)

    policy = PaperReadinessPolicy(
        minimum_calendar_days=int(os.environ.get("AIPRO_PAPER_MIN_DAYS", "30")),
        maximum_capture_gap_hours=int(os.environ.get("AIPRO_PAPER_MAX_GAP_HOURS", "36")),
        maximum_drawdown_pct=Decimal(os.environ.get("AIPRO_PAPER_MAX_DRAWDOWN_PCT", "10")),
        minimum_distinct_orders=int(os.environ.get("AIPRO_PAPER_MIN_DISTINCT_ORDERS", "1")),
    )
    monitor = AlpacaPaperReadinessMonitor(
        evidence_path=evidence_path,
        report_store=PaperReadinessReportStore(report_path),
        policy=policy,
    )
    report = monitor.evaluate(evaluated_at_utc=now)
    print(json.dumps({
        "qualifying": report.qualifying,
        "elapsed_calendar_days": report.elapsed_calendar_days,
        "covered_utc_dates": report.covered_utc_dates,
        "missing_utc_dates": report.missing_utc_dates,
        "maximum_capture_gap_hours": report.maximum_capture_gap_hours,
        "distinct_order_count": report.distinct_order_count,
        "maximum_drawdown_pct": report.maximum_drawdown_pct,
        "reasons": report.reasons,
        "fingerprint": report.fingerprint,
    }, sort_keys=True))
    return 0 if report.qualifying else 2


if __name__ == "__main__":
    raise SystemExit(main())
