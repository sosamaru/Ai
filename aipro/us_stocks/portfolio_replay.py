"""Chronological point-in-time replay. Synthetic runs never count as readiness."""
from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import tempfile
from typing import Iterable
from zoneinfo import ZoneInfo

from aipro.config import Settings
from aipro.intelligence.market_features import MarketBar
from aipro.us_stocks.portfolio_application import TradingApplication
from aipro.us_stocks.portfolio_market import Intelligence, MarketFrame, Quote, instant
from aipro.us_stocks.portfolio_policy import INITIAL_ALLOCATIONS, PortfolioPolicy

D = Decimal


def demo_frame(at: datetime | None = None, *, short_price: str = "10.46", long_price: str = "25") -> MarketFrame:
    """Invented symbols/prices and neutral intelligence for software verification."""
    at = at or datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    local = at.astimezone(ZoneInfo("America/New_York"))
    opened = local.replace(hour=9, minute=30, second=0, microsecond=0).astimezone(UTC)
    closed = local.replace(hour=16, minute=0, second=0, microsecond=0).astimezone(UTC)
    bars = []
    for index in range(30):
        price = 10 + index * 0.015
        bars.append(MarketBar((at - timedelta(minutes=30 - index)).isoformat(),
            price, price + 0.005, price - 0.005, price, 5000 if index >= 25 else 1000))
    dates, cursor = [], at.date() - timedelta(days=1)
    while len(dates) < 210:
        if cursor.weekday() < 5:
            dates.append(cursor)
        cursor -= timedelta(days=1)
    daily = tuple(MarketBar(datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=20).isoformat(),
        20 + index * 0.02, 20.03 + index * 0.02, 19.97 + index * 0.02, 20 + index * 0.02, 1000000)
        for index, day in enumerate(reversed(dates)))
    info = Intelligence(at, news_sentiment=0.1, source="SYNTHETIC_NEUTRAL_CONTEXT")
    quotes = (
        Quote("SIMS", at, D(short_price) - D("0.005"), D(short_price) + D("0.005"), D(1000), D(1000), D(5000000),
              intraday_bars=tuple(bars), intelligence=info),
        Quote("SIML", at, D(long_price) - D("0.01"), D(long_price) + D("0.01"), D(1000), D(1000), D(50000000),
              daily_bars=daily, intelligence=info),
    )
    return MarketFrame(at, D(1400), at, opened, closed, closed + timedelta(days=1), quotes, "SYNTHETIC_DEMO", True)


def demo_frames() -> tuple[MarketFrame, ...]:
    start = datetime(2026, 9, 14, 14, 30, tzinfo=UTC)
    first = demo_frame(start)
    # A profitable path, a later loss, and close flattening are illustrative only.
    return (first, demo_frame(start + timedelta(minutes=1), short_price="10.80", long_price="25.10"),
            demo_frame(start + timedelta(minutes=2), short_price="10.10", long_price="24.90"),
            replace(demo_frame(start.replace(hour=19, minute=56), short_price="10.15"),
                    quotes=tuple(replace(q, intraday_bars=()) for q in demo_frame(start.replace(hour=19, minute=56), short_price="10.15").quotes)))


def replay(frames: Iterable[MarketFrame], *, policy: PortfolioPolicy | None = None, forecaster=None) -> dict:
    """Isolated event-time run; validation failures never disappear from results."""
    count, blocked, fills, fingerprints, cycles = 0, [], [], [], []
    previous = None
    current = [datetime.now(UTC)]
    peaks = dict(INITIAL_ALLOCATIONS)
    drawdowns = {name: D(0) for name in INITIAL_ALLOCATIONS}
    synthetic = False
    with tempfile.TemporaryDirectory(prefix="aipro-us-replay-") as temp:
        app = TradingApplication(Settings(), policy=policy, db_path=Path(temp) / "portfolio.db", clock=lambda: current[0], forecaster=forecaster,
                                 use_environment_models=False)
        for frame in frames:
            count += 1
            if count > 100000:
                raise ValueError("replay exceeds 100,000 frames")
            stamp = instant(frame.as_of_utc)
            if previous is not None and stamp <= previous:
                raise ValueError("replay frames must be strictly chronological")
            previous, current[0] = stamp, stamp
            synthetic |= frame.synthetic
            fingerprints.append(frame.fingerprint)
            result = app.process_frame(frame)
            if not result["processed"]:
                blocked.append({"frame": count, "reason": result["reason"]})
                continue
            fills.extend(result["fills"])
            cycles.append(result)
            for name, book in result["status"]["sleeves"].items():
                equity = D(book["equity_krw"])
                peaks[name] = max(peaks[name], equity)
                drawdowns[name] = max(drawdowns[name], 1 - equity / peaks[name])
        if count == 0:
            raise ValueError("replay needs at least one frame")
        status = app.status()
        from aipro.us_stocks.performance_reporting import reports_from_cycles
        return {
            "schema": "us-dual-replay-v1", "paper_only": True, "live_ready": False,
            "qualifies_as_elapsed_paper_evidence": False,
            "synthetic": synthetic, "frames": count, "blocked_frames": blocked,
            "dataset_fingerprint": sha256("".join(fingerprints).encode()).hexdigest(),
            "policy_fingerprint": app.policy.fingerprint, "fills": fills,
            "model_id": getattr(app.forecaster, "model_id", "custom-forecast" if app.forecaster else "untrained-rule-baseline"),
            "maximum_observed_drawdown_pct": {name: str(value * 100) for name, value in drawdowns.items()},
            "final_status": status,
            "performance": reports_from_cycles(cycles) if cycles else {},
            "limitations": ["Event replay is not broker PAPER validation or proof of profitability.",
                "No fitted model is enabled by default; baseline strategies are untrained rules.",
                "KRW cash with per-trade FX conversion is a virtual cost model, not a real USD brokerage ledger.",
                "Historical prices, corporate actions, universe membership, calendar and intelligence must be point-in-time.",
                "Drawdown is sampled at supplied frames and can miss intraframe losses."],
        }


def load_jsonl(path: Path) -> Iterable[MarketFrame]:
    with path.open("rb") as handle:
        index = 0
        while line := handle.readline(8_000_001):
            index += 1
            if len(line) > 8_000_000:
                raise ValueError(f"line {index} exceeds 8 MB")
            if line.strip():
                try:
                    yield MarketFrame.from_dict(json.loads(line))
                except RecursionError:
                    raise ValueError(f"line {index} nesting exceeds supported depth") from None


def run_demo(output: Path | None = None) -> int:
    report = replay(demo_frames())
    print("SYNTHETIC DEMO · 실제 시세/수익률 검증 아님 · 외부 자금 상한 1,000,000원")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0
