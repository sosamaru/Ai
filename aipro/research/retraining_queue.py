"""Bounded trigger queue; fitting runs in a separate worker, never the order loop."""
from __future__ import annotations

from datetime import timedelta
import json
from pathlib import Path

from aipro.core.adaptive_risk import retraining_reasons
from aipro.core.evidence import canonical, fingerprint, instant, integer
from aipro.sqlite_utils import connect


class RetrainingQueue:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS retraining_jobs(id TEXT PRIMARY KEY, symbol TEXT NOT NULL, resolved INTEGER NOT NULL, requested TEXT NOT NULL, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS retraining_events(id TEXT NOT NULL, phase TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(id,phase))")
            for table in ("retraining_jobs", "retraining_events"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'append-only retraining'); END")

    def request(self, *, symbol: str, total_resolved: int, now, archive: Path, output_root: Path,
                experiment_ledger: Path, drift: float = 0, brier_change: float = 0,
                regime_changed=False, ev_degraded=False):
        integer(total_resolved, "resolved count", 0, 10000000)
        stamp = instant(now)
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            previous = db.execute("SELECT resolved,requested FROM retraining_jobs WHERE symbol=? ORDER BY requested DESC LIMIT 1", (symbol,)).fetchone()
            elapsed = (stamp - instant(previous[1])).total_seconds() if previous else 86400
            new_rows = total_resolved - previous[0] if previous else total_resolved
            if new_rows < 0:
                raise ValueError("resolved observation count cannot decrease")
            reasons = retraining_reasons(new_resolved_rows=new_rows, since_last_seconds=elapsed,
                drift=drift, brier_change=brier_change, regime_changed=regime_changed, ev_degraded=ev_degraded)
            if not reasons:
                return None
            if db.execute("SELECT COUNT(*) FROM retraining_jobs j WHERE NOT EXISTS(SELECT 1 FROM retraining_events e WHERE e.id=j.id AND e.phase IN ('COMPLETE','FAILED'))").fetchone()[0] >= 2:
                return None
            body = {"symbol": symbol, "total_resolved": total_resolved, "at": stamp.isoformat(),
                    "archive": str(archive.resolve()), "output_root": str(output_root.resolve()),
                    "experiment_ledger": str(experiment_ledger.resolve()), "reasons": reasons,
                    "candidate_only": True, "execution_authority": False}
            key = fingerprint(body)
            db.execute("INSERT INTO retraining_jobs VALUES(?,?,?,?,?)", (key, symbol, total_resolved, stamp.isoformat(), canonical(body)))
            return key

    def run_next(self, trainer=None):
        if trainer is None:
            from aipro.us_stocks.model_training import train_from_archive
            trainer = train_from_archive
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT j.id,j.payload FROM retraining_jobs j WHERE NOT EXISTS(SELECT 1 FROM retraining_events e WHERE e.id=j.id) ORDER BY requested LIMIT 1").fetchone()
            if row is None:
                return {"phase": "IDLE", "candidate_only": True}
            key, raw = row
            db.execute("INSERT INTO retraining_events VALUES(?,?,?)", (key, "STARTED", canonical({"claim": "single_worker"})))
        body = json.loads(raw)
        try:
            result = trainer(Path(body["archive"]), symbol=body["symbol"],
                output_dir=Path(body["output_root"]) / key, experiment_id="retrain-" + key,
                ledger_path=Path(body["experiment_ledger"]), calibration_method="sigmoid")
            phase = "COMPLETE" if result == 0 else "FAILED"
            evidence = {"return_code": result, "candidate_only": True, "promotion_performed": False}
        except (OSError, ValueError, RuntimeError) as exc:
            phase, evidence = "FAILED", {"error_type": type(exc).__name__, "candidate_only": True}
        # A terminated worker's STARTED claim remains visible and is not silently
        # retried against a potentially exposed final holdout.
        with connect(self.path) as db:
            db.execute("INSERT INTO retraining_events VALUES(?,?,?)", (key, phase, canonical(evidence)))
        return {"job_id": key, "phase": phase, **evidence}
