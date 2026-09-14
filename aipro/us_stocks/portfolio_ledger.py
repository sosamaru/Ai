"""Atomic, restart-safe virtual KRW books. No broker or transfer authority."""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from aipro.sqlite_utils import connect
from aipro.us_stocks.portfolio_policy import (
    EXTERNAL_FUNDING_CAP_KRW, INITIAL_ALLOCATIONS, PortfolioPolicy, number,
)


def canonical(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False)


def initial_state(policy: PortfolioPolicy) -> dict:
    return {
        "schema": 1,
        "policy_fingerprint": policy.fingerprint,
        "external_contributed_krw": str(EXTERNAL_FUNDING_CAP_KRW),
        "total_peak_krw": str(EXTERNAL_FUNDING_CAP_KRW),
        "global_halt": "",
        "last_frame_utc": "",
        "last_source_synthetic": None,
        "last_status": {},
        "sleeves": {
            name: {
                "cash": str(amount), "realized_pnl": "0", "positions": {},
                "pending": [], "baseline": str(amount), "peak": str(amount),
                "day": "", "entries_today": 0, "entered_symbols_today": [],
                "halt": "", "target_day": "", "last_review": "",
            } for name, amount in INITIAL_ALLOCATIONS.items()
        },
    }


def validate_accounting(state: dict, policy: PortfolioPolicy) -> None:
    """Reconcile each book to its own funding plus realized net P&L."""
    if state["schema"] != 1 or state["policy_fingerprint"] != policy.fingerprint:
        raise RuntimeError("portfolio schema/policy mismatch; explicit migration required")
    if number(state["external_contributed_krw"]) != EXTERNAL_FUNDING_CAP_KRW:
        raise RuntimeError("external funding boundary violated")
    if set(state["sleeves"]) != set(INITIAL_ALLOCATIONS):
        raise RuntimeError("portfolio sleeve boundary violated")
    for name, book in state["sleeves"].items():
        cash = number(book["cash"])
        pending = sum((number(item["amount"]) for item in book["pending"]), Decimal(0))
        cost = Decimal(0)
        for position in book["positions"].values():
            if number(position["qty"]) <= 0 or number(position["entry_usd"]) <= 0:
                raise RuntimeError("invalid position")
            cost += number(position["cost"])
        realized = number(book["realized_pnl"], minimum=Decimal("-1000000000000000"))
        expected = INITIAL_ALLOCATIONS[name] + realized
        if abs(cash + pending + cost - expected) > Decimal("0.000001"):
            raise RuntimeError(f"{name} accounting mismatch")
        number(book["baseline"])
        number(book["peak"])
        if type(book["entries_today"]) is not int or book["entries_today"] < 0:
            raise RuntimeError("invalid entry counter")


class PortfolioLedger:
    def __init__(self, path: Path, policy: PortfolioPolicy) -> None:
        self.path, self.policy = Path(path), policy
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if tables - {"us_dual_state", "us_dual_events", "sqlite_sequence"}:
                raise RuntimeError("use a dedicated US dual DB; other domain state detected")
            db.execute("CREATE TABLE IF NOT EXISTS us_dual_state(id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL, digest TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS us_dual_events(seq INTEGER PRIMARY KEY AUTOINCREMENT, event_key TEXT UNIQUE NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL)")
            for action in ("UPDATE", "DELETE"):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS us_dual_no_{action.lower()} BEFORE {action} ON us_dual_events BEGIN SELECT RAISE(ABORT, 'append-only audit'); END")
            if db.execute("SELECT id FROM us_dual_state WHERE id=1").fetchone() is None:
                if db.execute("SELECT COUNT(*) FROM us_dual_events").fetchone()[0]:
                    raise RuntimeError("state missing in existing ledger; refusing to refund")
                state = initial_state(policy)
                raw = canonical(state)
                db.execute("INSERT INTO us_dual_state VALUES(1,?,?)", (raw, sha256(raw.encode()).hexdigest()))
                self.record(db, "funding", "INITIAL_FUNDING", {
                    "external_contributed_krw": "1000000", "short": "200000", "long": "800000",
                    "paper_only": True,
                })
            self._load(db)

    def _load(self, db) -> dict:
        row = db.execute("SELECT payload,digest FROM us_dual_state WHERE id=1").fetchone()
        if row is None or sha256(row[0].encode()).hexdigest() != row[1]:
            raise RuntimeError("portfolio state missing or corrupt")
        state = json.loads(row[0])
        validate_accounting(state, self.policy)
        return state

    @contextmanager
    def transaction(self):
        with connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            state = self._load(db)
            yield db, state
            validate_accounting(state, self.policy)
            raw = canonical(state)
            db.execute("UPDATE us_dual_state SET payload=?,digest=? WHERE id=1", (raw, sha256(raw.encode()).hexdigest()))

    def read(self) -> dict:
        with connect(self.path) as db:
            return self._load(db)

    @staticmethod
    def record(db, key: str, kind: str, payload: dict) -> None:
        db.execute("INSERT INTO us_dual_events(event_key,kind,payload) VALUES(?,?,?)", (key, kind, canonical(payload)))

    def events(self) -> tuple[dict, ...]:
        with connect(self.path) as db:
            return tuple({"key": key, "kind": kind, **json.loads(raw)} for key, kind, raw in
                         db.execute("SELECT event_key,kind,payload FROM us_dual_events ORDER BY seq"))

    def contribute(self, amount_krw: Decimal) -> None:
        number(amount_krw)
        raise RuntimeError("lifetime external funding already equals KRW 1,000,000; deposits disabled")
