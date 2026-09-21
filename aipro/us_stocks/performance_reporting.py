"""Cost-inclusive per-sleeve reports from the existing immutable cycle journal."""
from __future__ import annotations

from datetime import timedelta
import json
from zoneinfo import ZoneInfo

from aipro.core.evidence import instant
from aipro.core.performance import ClosedTrade, EquityObservation, performance_report
from aipro.us_stocks.portfolio_policy import INITIAL_ALLOCATIONS


def reports_from_cycles(cycles) -> dict:
    cycles = tuple(cycles)
    if not cycles or len(cycles) > 100000:
        raise ValueError("one to 100,000 ordered cycles required")
    result = {}
    for name, funding in INITIAL_ALLOCATIONS.items():
        first = instant(cycles[0]["status"]["as_of_utc"])
        points = [EquityObservation((first - timedelta(microseconds=1)).isoformat(), float(funding))]
        trades, fees, slippage, turnover = [], 0.0, 0.0, 0.0
        missing_cost_evidence = False
        for cycle in cycles:
            stamp = cycle["status"]["as_of_utc"]
            book = cycle["status"]["sleeves"][name]
            equity = float(book["equity_krw"])
            cash = float(book["cash_krw"]) + float(book["unsettled_krw"])
            points.append(EquityObservation(stamp, equity, max(0, min(1, 1 - cash / equity)) if equity else 0))
            for fill in cycle["fills"]:
                if fill["sleeve"] != name:
                    continue
                fees += float(fill["costs_krw"])
                slippage += float(fill.get("slippage_krw", 0))
                turnover += float(fill.get("turnover_krw", 0))
                missing_cost_evidence |= "slippage_krw" not in fill
                if fill["side"] == "SELL" and not fill.get("partial"):
                    if fill.get("episode_cost_krw") is None:
                        missing_cost_evidence = True
                        continue
                    trades.append(ClosedTrade(stamp, float(fill["episode_pnl_krw"]), float(fill["episode_cost_krw"]),
                                              fill.get("regime", "unknown"), fill.get("model_id", "unattributed")))
        report = performance_report(points, trades, domain="us_stock", fee_cost=fees, slippage_cost=slippage,
                                    turnover_notional=turnover)
        latest = cycles[-1]["status"]["sleeves"][name]
        report.update(sleeve=name, baseline=float(latest["baseline_equity_krw"]),
                      today_return=float(latest["daily_return_pct"]) / 100,
                      risk_state=latest.get("adaptive_risk", {}),
                      prediction_calibration=None, champion_performance=report["model_performance"],
                      challenger_performance={}, legacy_cost_evidence_incomplete=missing_cost_evidence,
                      paper_only=True, live_ready=False, qualifies_as_elapsed_paper_evidence=False,
                      synthetic=any(c["synthetic"] for c in cycles))
        result[name] = report
    return result


def finalize_daily_reports(ledger, now) -> int:
    """Finalize observed past KST days on the first later cycle; no fabricated days."""
    today = instant(now).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
    with ledger.transaction() as (db, state):
        rows = db.execute("SELECT payload FROM us_dual_events WHERE kind='CYCLE' ORDER BY seq LIMIT 100001").fetchall()
        if len(rows) > 100000:
            raise ValueError("daily report archive budget reached; archive reviewed history first")
        cycles = [json.loads(row[0]) for row in rows]
        count = 0
        for index, cycle in enumerate(cycles):
            day = instant(cycle["status"]["as_of_utc"]).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
            next_day = (instant(cycles[index + 1]["status"]["as_of_utc"]).astimezone(ZoneInfo("Asia/Seoul")).date().isoformat()
                        if index + 1 < len(cycles) else today)
            if day >= today or day == next_day:
                continue
            key = "daily-report:" + day
            if db.execute("SELECT 1 FROM us_dual_events WHERE event_key=?", (key,)).fetchone():
                continue
            reports = reports_from_cycles(cycles[:index + 1])
            ledger.record(db, key, "DAILY_REPORT", {"day_kst": day, "reports": reports})
            count += 1
        return count
