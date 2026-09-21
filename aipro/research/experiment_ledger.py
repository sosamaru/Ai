"""Append-only experiment budgets and single-use, domain-wide holdout leases.

An opened interval remains consumed even if fitting/evaluation crashes. Changing
dataset IDs, symbol names, policies or output directories does not unlock it.
This protects cooperating local runners; it is not an ACL against database deletion.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from aipro.core.evidence import canonical, digest, domain, fingerprint, instant, integer
from aipro.sqlite_utils import connect


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    domain: str
    dataset_fingerprint: str
    code_fingerprint: str
    feature_schema: str
    failure_policy: dict
    trial_budget: int = 8

    def __post_init__(self):
        domain(self.domain)
        digest(self.dataset_fingerprint)
        digest(self.code_fingerprint)
        integer(self.trial_budget, "trial budget", 1, 20)
        if not self.experiment_id.strip() or not self.feature_schema.strip() or not self.failure_policy:
            raise ValueError("experiment identity, feature schema and failure rules are required")
        canonical(asdict(self))


class ExperimentLedger:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS research_experiments (id TEXT PRIMARY KEY, domain TEXT NOT NULL, spec TEXT NOT NULL, budget INTEGER NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS research_trials (experiment TEXT NOT NULL, candidate TEXT NOT NULL, config TEXT NOT NULL, PRIMARY KEY(experiment,candidate))")
            db.execute("CREATE TABLE IF NOT EXISTS research_holdouts (experiment TEXT UNIQUE NOT NULL, domain TEXT NOT NULL, start TEXT NOT NULL, end TEXT NOT NULL, candidate TEXT NOT NULL, model TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS research_results (experiment TEXT PRIMARY KEY, evidence TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS research_failures (seq INTEGER PRIMARY KEY, experiment TEXT NOT NULL, error_type TEXT NOT NULL)")
            for table in ("research_experiments", "research_trials", "research_holdouts", "research_results", "research_failures"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'immutable research evidence'); END")

    def register(self, spec: ExperimentSpec):
        raw = canonical(asdict(spec))
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT spec FROM research_experiments WHERE id=?", (spec.experiment_id,)).fetchone()
            if existing:
                if existing[0] != raw:
                    raise ValueError("failure criteria changed; create a new experiment")
                return
            db.execute("INSERT INTO research_experiments VALUES(?,?,?,?)", (spec.experiment_id, spec.domain, raw, spec.trial_budget))

    def reserve_trial(self, experiment_id: str, candidate: str, configuration: dict):
        if not candidate.strip():
            raise ValueError("candidate required")
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT budget FROM research_experiments WHERE id=?", (experiment_id,)).fetchone()
            if not row:
                raise ValueError("preregister experiment before fitting")
            if db.execute("SELECT 1 FROM research_holdouts WHERE experiment=?", (experiment_id,)).fetchone():
                raise ValueError("holdout already opened; tuning is closed")
            count = db.execute("SELECT COUNT(*) FROM research_trials WHERE experiment=?", (experiment_id,)).fetchone()[0]
            if count >= row[0]:
                raise ValueError("predeclared search budget exhausted")
            db.execute("INSERT INTO research_trials VALUES(?,?,?)", (experiment_id, candidate, canonical(configuration)))

    def open_holdout(self, experiment_id: str, candidate: str, start, end, model_fingerprint: str):
        begin, stop = instant(start).isoformat(), instant(end).isoformat()
        if begin >= stop:
            raise ValueError("holdout interval must increase")
        digest(model_fingerprint)
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT domain FROM research_experiments WHERE id=?", (experiment_id,)).fetchone()
            if not row or not db.execute("SELECT 1 FROM research_trials WHERE experiment=? AND candidate=?", (experiment_id, candidate)).fetchone():
                raise ValueError("registered trial required before final evaluation")
            if db.execute("SELECT 1 FROM research_holdouts WHERE domain=? AND start<=? AND end>=?", (row[0], stop, begin)).fetchone():
                raise ValueError("final holdout overlaps consumed evidence; use a later untouched interval")
            db.execute("INSERT INTO research_holdouts VALUES(?,?,?,?,?,?)", (experiment_id, row[0], begin, stop, candidate, model_fingerprint))

    def finish(self, experiment_id: str, evidence: dict):
        with connect(self.path) as db:
            if not db.execute("SELECT 1 FROM research_holdouts WHERE experiment=?", (experiment_id,)).fetchone():
                raise ValueError("no reserved final evaluation")
            db.execute("INSERT INTO research_results VALUES(?,?)", (experiment_id, canonical(evidence)))
        return fingerprint(evidence)

    def record_failure(self, experiment_id: str, error_type: str) -> None:
        with connect(self.path) as db:
            db.execute("INSERT INTO research_failures(experiment,error_type) VALUES(?,?)", (experiment_id, error_type))
