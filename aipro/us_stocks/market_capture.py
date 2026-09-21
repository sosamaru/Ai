"""Prospective public-frame archive shared by canonical PAPER and later replay.

The capture clock is independent of the supplied quote clock. Integrity is not
provider authentication; an imported file is still an untrusted data source.
"""
from pathlib import Path
import json

from aipro.core.evidence import canonical, instant
from aipro.sqlite_utils import connect
from aipro.us_stocks.portfolio_market import MarketFrame


class FrameArchive:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.path) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {"us_market_capture"}:
                raise ValueError("market capture requires a dedicated database")
            db.execute("CREATE TABLE IF NOT EXISTS us_market_capture (fingerprint TEXT PRIMARY KEY, observed TEXT UNIQUE NOT NULL, captured TEXT NOT NULL, payload TEXT NOT NULL)")
            for action in ("UPDATE", "DELETE"):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS market_capture_no_{action} BEFORE {action} ON us_market_capture BEGIN SELECT RAISE(ABORT,'append-only market capture'); END")

    def append(self, frame: MarketFrame, *, captured_at, max_age_seconds: int = 60) -> bool:
        now, stamp = instant(captured_at), instant(frame.as_of_utc)
        if type(max_age_seconds) is not int or not 1 <= max_age_seconds <= 300:
            raise ValueError("bounded capture freshness required")
        if frame.synthetic or not 0 <= (now - stamp).total_seconds() <= max_age_seconds:
            raise ValueError("prospective capture requires current non-synthetic frames")
        if any(not 0 <= (stamp - instant(q.as_of_utc)).total_seconds() <= max_age_seconds for q in frame.quotes):
            raise ValueError("capture contains stale or future quotes")
        raw = canonical(frame.to_dict())
        if len(raw.encode("utf-8")) > 8_000_000:
            raise ValueError("capture exceeds byte budget")
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM us_market_capture WHERE fingerprint=?", (frame.fingerprint,)).fetchone():
                return False
            last = db.execute("SELECT observed,captured FROM us_market_capture ORDER BY observed DESC LIMIT 1").fetchone()
            if last and (stamp <= instant(last[0]) or now < instant(last[1])):
                raise ValueError("capture clocks cannot reverse or replace an observed frame")
            db.execute("INSERT INTO us_market_capture VALUES(?,?,?,?)",
                       (frame.fingerprint, stamp.isoformat(), now.isoformat(), raw))
        return True

    def export(self, path: Path) -> int:
        if path.resolve() == self.path.resolve():
            raise ValueError("export must not overwrite its capture database")
        path.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids overwriting another dataset or inspected holdout.
        count = 0
        with connect(self.path) as db, path.open("x", encoding="utf-8") as out:
            for key, raw in db.execute("SELECT fingerprint,payload FROM us_market_capture ORDER BY observed"):
                frame = MarketFrame.from_dict(json.loads(raw))
                if frame.fingerprint != key:
                    raise ValueError("capture integrity mismatch")
                out.write(raw + "\n")
                count += 1
        return count


class CapturingMarketData:
    def __init__(self, delegate, archive: FrameArchive, *, clock, max_age_seconds=60):
        self.delegate, self.archive, self.clock = delegate, archive, clock
        self.max_age_seconds = max_age_seconds

    def frame(self) -> MarketFrame:
        frame = self.delegate.frame()
        self.archive.append(frame, captured_at=self.clock(), max_age_seconds=self.max_age_seconds)
        return frame
