"""Isolated prospective PAPER books and automatic, evidence-gated replacement.

Each candidate gets its own virtual 200k/800k book. These independent experiments
are not real additional owner funding. The selected provider has no broker or
core risk reference. A promotion changes only the next prediction's source.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
import json
import os
from pathlib import Path

from aipro.core.evidence import canonical, digest, fingerprint, instant
from aipro.core.performance import ClosedTrade, EquityObservation
from aipro.intelligence.calibration import reliability_report
from aipro.intelligence.promotion import PerformanceEvidence, PaperPromotionStore, PromotionPolicy
from aipro.sqlite_utils import connect
from aipro.us_stocks.model_artifact import ArtifactForecastProvider, _unique_object, load_artifact
from aipro.us_stocks.model_features import model_features
from aipro.us_stocks.performance_reporting import reports_from_cycles


def read_evidence(path: Path, expected_fingerprint: str) -> PerformanceEvidence:
    digest(expected_fingerprint)
    with path.open("rb") as handle:
        raw = handle.read(8000001)
    if len(raw) > 8000000:
        raise ValueError("OOS portfolio evidence exceeds 8 MB")
    body = json.loads(raw, object_pairs_hook=_unique_object)
    if fingerprint(body) != expected_fingerprint:
        raise ValueError("OOS portfolio evidence pin mismatch")
    body["points"] = tuple(EquityObservation(**p) for p in body["points"])
    body["trades"] = tuple(ClosedTrade(**t) for t in body["trades"])
    return PerformanceEvidence(**body)


class ShadowCohort:
    def __init__(self, providers, oos, *, directory, settings, policy, clock):
        from aipro.us_stocks.portfolio_application import TradingApplication
        self.providers = {p.artifact.fingerprint: p for p in providers}
        self.oos = dict(oos)
        if not 2 <= len(self.providers) <= 6 or set(self.providers) != set(self.oos):
            raise ValueError("cohort needs 2 to 6 distinct models with matching OOS evidence")
        bodies = [p.artifact.payload for p in providers]
        for key in ("symbol", "feature_schema", "horizon_seconds", "policy_fingerprint", "synthetic"):
            if len({b[key] for b in bodies}) != 1:
                raise ValueError("cohort model contracts differ")
        for key, evidence in self.oos.items():
            body = self.providers[key].artifact.payload
            if (evidence.model_fingerprint != key or evidence.domain != "us_stock" or evidence.phase != "oos"
                    or evidence.synthetic or body["synthetic"] or body["policy_fingerprint"] != policy.fingerprint):
                raise ValueError("cohort requires non-synthetic, matched, cost-aware OOS evidence")
            if instant(evidence.points[0].at) <= instant(body["validation_end_utc"]):
                raise ValueError("portfolio OOS must follow model selection holdout")
        self.clock, self.policy = clock, policy
        self.promotion_policy = PromotionPolicy()
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.store = PaperPromotionStore(directory / "promotions.sqlite3")
        if self.store.current("us_stock") is None:
            self.store.initialize("us_stock", next(iter(self.providers)), self.promotion_policy)
        if self.store.current("us_stock") not in self.providers:
            raise ValueError("pinned cohort cannot remove its active champion")
        self.apps = {key: TradingApplication(settings, policy=policy, db_path=directory / (key + ".sqlite3"),
                    forecaster=provider, clock=clock, use_environment_models=False) for key, provider in self.providers.items()}
        self.path = directory / "capture.sqlite3"
        self.last_reason, self.last_report = "cohort_not_evaluated", {}
        self.directory = directory
        with connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS shadow_capture(model TEXT NOT NULL, frame TEXT NOT NULL, observed TEXT NOT NULL, captured TEXT NOT NULL, probability REAL, PRIMARY KEY(model,frame))")
            db.execute("CREATE TABLE IF NOT EXISTS shadow_outcomes(model TEXT NOT NULL, start TEXT NOT NULL, probability REAL NOT NULL, label INTEGER NOT NULL, PRIMARY KEY(model,start))")
            db.execute("CREATE TABLE IF NOT EXISTS shadow_pending(model TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS shadow_reviews(day TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            for table in ("shadow_capture", "shadow_outcomes", "shadow_reviews"):
                for action in ("UPDATE", "DELETE"):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{action} BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'append-only shadow evidence'); END")

    @property
    def model_id(self):
        return self.providers[self.store.current("us_stock")].model_id

    def forecast(self, quote, feature_fingerprint):
        return None

    def forecast_frame(self, quote, frame, policy, feature_fingerprint):
        provider = self.providers[self.store.current("us_stock")]
        result = provider.forecast_frame(quote, frame, policy, feature_fingerprint)
        self.last_reason = provider.last_reason
        return result

    def observe(self, frame):
        now, at = instant(self.clock()), instant(frame.as_of_utc)
        if frame.synthetic or not 0 <= (now - at).total_seconds() <= self.policy.frame_max_age_seconds:
            raise ValueError("prospective shadow needs current non-synthetic frames")
        symbol = next(iter(self.providers.values())).artifact.payload["symbol"]
        quote = next((q for q in frame.quotes if q.symbol == symbol), None)
        if quote is None:
            raise ValueError("shadow candidate symbol missing")
        for key, app in self.apps.items():
            if at <= instant(self.oos[key].points[-1].at):
                raise ValueError("shadow must follow frozen OOS portfolio evidence")
            result = app.process_frame(frame)
            if not result["processed"]:
                continue
            probability = None
            try:
                _, feature_fp = model_features(quote, at)
                forecast = self.providers[key].forecast_frame(quote, frame, self.policy, feature_fp, enforce_threshold=False)
                probability = forecast.win_probability if forecast else None
            except ValueError:
                pass
            with connect(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute("INSERT INTO shadow_capture VALUES(?,?,?,?,?)", (key, frame.fingerprint, at.isoformat(), now.isoformat(), probability))
                pending = db.execute("SELECT payload FROM shadow_pending WHERE model=?", (key,)).fetchone()
                resolved = False
                if pending:
                    item = json.loads(pending[0])
                    if at >= instant(item["end"]):
                        if at == instant(item["end"]) and quote.tradable and quote.bid_size > 0 and item["session"] == instant(frame.session_open_utc).isoformat():
                            db.execute("INSERT INTO shadow_outcomes VALUES(?,?,?,?)", (key, item["start"], item["probability"],
                                int(float(quote.bid * frame.usd_krw) > item["entry"])))
                            resolved = True
                        db.execute("DELETE FROM shadow_pending WHERE model=?", (key,))
                        pending = None
                if pending is None and not resolved and probability is not None and quote.tradable and quote.ask_size > 0:
                    end = at + timedelta(seconds=self.providers[key].artifact.payload["horizon_seconds"])
                    if end < instant(frame.session_close_utc):
                        payload = {"start": at.isoformat(), "end": end.isoformat(), "probability": probability,
                                   "session": instant(frame.session_open_utc).isoformat(), "entry": float(quote.ask * frame.usd_krw)}
                        db.execute("INSERT INTO shadow_pending VALUES(?,?)", (key, canonical(payload)))
        # Once per observed calendar day; repeated polling is not new evidence.
        day = at.date().isoformat()
        with connect(self.path) as db:
            if db.execute("SELECT 1 FROM shadow_reviews WHERE day=?", (day,)).fetchone():
                return
        decisions = []
        champion = self.store.current("us_stock")
        champion_evidence = self._evidence(champion)
        for key in sorted(self.providers):
            if key == champion:
                continue
            evidence = self._evidence(key)
            if evidence is None or champion_evidence is None:
                continue
            decision = self.store.compare_and_promote(self.oos[champion], self.oos[key], evidence, now=now,
                policy=self.promotion_policy, champion_shadow=champion_evidence)
            decisions.append(decision)
            if decision["approved"]:
                break
        with connect(self.path) as db:
            db.execute("INSERT OR IGNORE INTO shadow_reviews VALUES(?,?)", (day, canonical(decisions)))
        self.last_report = {"champion": self.store.current("us_stock"), "decisions": decisions, "paper_only": True}
        archive = os.getenv("AIPRO_US_TRAINING_ARCHIVE", "").strip()
        if archive:
            champion_key = self.store.current("us_stock")
            with connect(self.path) as db:
                count = db.execute("SELECT COUNT(*) FROM shadow_outcomes WHERE model=?", (champion_key,)).fetchone()[0]
            report = self.apps[champion_key].ledger.read().get("monitors", {}).get("short", {})
            from aipro.research.retraining_queue import RetrainingQueue
            queue = RetrainingQueue(self.directory / "retraining.sqlite3")
            self.last_report["retraining_job"] = queue.request(symbol=symbol, total_resolved=count, now=now,
                archive=Path(archive), output_root=self.directory / "candidates",
                experiment_ledger=self.directory / "research_experiments.sqlite3",
                drift=report.get("feature_drift", 0), ev_degraded=report.get("health", {}).get("mode") in {"REDUCED_RISK", "PAPER_ONLY"})

    def _evidence(self, key):
        events = [event for event in self.apps[key].ledger.events() if event["kind"] == "CYCLE"]
        if len(events) < 2:
            return None
        with connect(self.path) as db:
            captures = db.execute("SELECT MIN(captured),MAX(captured),COUNT(*) FROM shadow_capture WHERE model=?", (key,)).fetchone()
            outcomes = db.execute("SELECT probability,label FROM shadow_outcomes WHERE model=? ORDER BY start", (key,)).fetchall()
        if not captures[0] or len(outcomes) < 30 or captures[2] != len(events):
            return None
        points, trades = [], []
        for event in events:
            book = event["status"]["sleeves"]["short"]
            at = event["status"]["as_of_utc"]
            points.append(EquityObservation(at, float(book["equity_krw"])))
            for fill in event["fills"]:
                if fill["sleeve"] == "short" and fill["side"] == "SELL" and not fill.get("partial"):
                    trades.append(ClosedTrade(at, float(fill["episode_pnl_krw"]), float(fill["episode_cost_krw"]),
                                              fill.get("regime", "unknown"), key))
        report = reports_from_cycles(events)["short"]
        calibration = reliability_report([row[0] for row in outcomes], [row[1] for row in outcomes])
        # A post-hoc fee haircut is not a stressed portfolio replay: liquidity,
        # sizing and exits change with costs. With no such evidence attached,
        # this mandatory promotion gate stays closed.
        stress = 0.0
        return PerformanceEvidence("us_stock", key, fingerprint([event["frame_fingerprint"] for event in events]),
            "shadow", tuple(points), tuple(trades), report["fee_cost"], report["slippage_cost"],
            report["turnover"] * sum(p.equity for p in points) / len(points), calibration["brier_score"], calibration["ece"],
            stress, self.oos[key].positive_walk_forward_fraction, False, captures[0], captures[1])


def load_cohort(path, *, expected_fingerprint, directory, settings, policy, clock):
    with path.open("rb") as handle:
        raw = handle.read(100001)
    if len(raw) > 100000:
        raise ValueError("cohort manifest exceeds size limit")
    body = json.loads(raw, object_pairs_hook=_unique_object)
    digest(expected_fingerprint)
    if set(body) != {"schema", "models"} or body["schema"] != "aipro-shadow-cohort-v1" or fingerprint(body) != expected_fingerprint:
        raise ValueError("cohort manifest schema or pin mismatch")
    if not 2 <= len(body["models"]) <= 6:
        raise ValueError("cohort model count outside bounds")
    def local(name):
        item = (path.parent / name).resolve()
        if not item.is_relative_to(path.parent.resolve()):
            raise ValueError("cohort files must remain inside reviewed directory")
        return item
    providers, evidence = [], {}
    for item in body["models"]:
        if set(item) != {"path", "fingerprint", "oos_path", "oos_fingerprint"}:
            raise ValueError("invalid cohort member")
        artifact = load_artifact(local(item["path"]), expected_fingerprint=item["fingerprint"])
        providers.append(ArtifactForecastProvider(artifact))
        evidence[artifact.fingerprint] = read_evidence(local(item["oos_path"]), item["oos_fingerprint"])
    return ShadowCohort(providers, evidence, directory=directory, settings=settings, policy=policy, clock=clock)
