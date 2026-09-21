"""Multi-metric, paired OOS + elapsed shadow gates for PAPER replacements.

Daily portfolio returns, not selectively traded markouts, are compared. No LIVE
state or authorization is created. Evidence provenance must be independently
verified by the caller; fingerprints are not signatures.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from pathlib import Path

from aipro.core.evidence import canonical, digest, domain, finite, fingerprint, instant, integer
from aipro.core.performance import ClosedTrade, EquityObservation, performance_report
from aipro.research.robust_statistics import BootstrapPolicy, mean_interval, paired_improvement
from aipro.sqlite_utils import connect


@dataclass(frozen=True)
class PromotionPolicy:
    min_trades: int = 100
    min_days: int = 30
    max_drawdown: float = .10
    max_brier: float = .25
    max_ece: float = .10
    min_regimes: int = 2
    min_regime_trades: int = 20
    max_turnover_ratio: float = 1.25
    min_ev_improvement: float = .0001
    bootstrap: BootstrapPolicy = BootstrapPolicy()

    def __post_init__(self):
        integer(self.min_trades, "min trades", 30, 10000)
        integer(self.min_days, "min days", 30, 3650)
        integer(self.min_regimes, "min regimes", 2, 8)
        integer(self.min_regime_trades, "min regime trades", 10, 1000)
        for name in ("max_drawdown", "max_brier", "max_ece", "min_ev_improvement"):
            finite(getattr(self, name), name, 0, 1)
        finite(self.max_turnover_ratio, "turnover ratio", 1, 2)


@dataclass(frozen=True)
class PerformanceEvidence:
    domain: str
    model_fingerprint: str
    dataset_fingerprint: str
    phase: str
    points: tuple[EquityObservation, ...]
    trades: tuple[ClosedTrade, ...]
    fees: float
    slippage: float
    turnover: float
    brier: float
    ece: float
    stress_net_return: float
    positive_walk_forward_fraction: float
    synthetic: bool
    captured_from: str
    captured_until: str

    def __post_init__(self):
        domain(self.domain)
        digest(self.model_fingerprint)
        digest(self.dataset_fingerprint)
        if self.phase not in {"oos", "paper", "shadow"} or type(self.synthetic) is not bool:
            raise ValueError("explicit validation phase and provenance required")
        if not self.points or len(self.points) > 20000 or len(self.trades) > 20000:
            raise ValueError("bounded nonempty performance evidence required")
        if instant(self.captured_until) < instant(self.captured_from):
            raise ValueError("capture interval inverted")
        for name in ("fees", "slippage", "turnover"):
            finite(getattr(self, name), name, 0)
        for name in ("brier", "ece", "positive_walk_forward_fraction"):
            finite(getattr(self, name), name, 0, 1)
        finite(self.stress_net_return, "stress return", -1)

    def report(self):
        return performance_report(self.points, self.trades, domain=self.domain, fee_cost=self.fees,
                                  slippage_cost=self.slippage, turnover_notional=self.turnover)


def evaluate_promotion(champion: PerformanceEvidence, challenger: PerformanceEvidence,
                       shadow: PerformanceEvidence, *, now, policy=PromotionPolicy(),
                       champion_shadow: PerformanceEvidence | None = None):
    if len({e.domain for e in (champion, challenger, shadow)}) != 1:
        raise ValueError("promotion domains cannot mix")
    if champion.model_fingerprint == challenger.model_fingerprint or challenger.model_fingerprint != shadow.model_fingerprint:
        raise ValueError("candidate identity mismatch")
    if champion.dataset_fingerprint != challenger.dataset_fingerprint:
        raise ValueError("comparison requires identical OOS market archive")
    if champion.phase != "oos" or challenger.phase != "oos" or shadow.phase not in {"paper", "shadow"}:
        raise ValueError("OOS followed by separate PAPER/shadow evidence required")
    if tuple(p.at for p in champion.points) != tuple(p.at for p in challenger.points):
        raise ValueError("portfolio comparisons must share exact timestamps, including no-trade periods")
    now = instant(now)
    if instant(shadow.points[0].at) <= instant(challenger.points[-1].at):
        raise ValueError("shadow period must follow OOS evaluation")
    if any(instant(e.captured_until) > now or instant(e.points[-1].at) > now for e in (champion, challenger, shadow)):
        raise ValueError("future evidence cannot promote a model")
    reports = [e.report() for e in (champion, challenger, shadow)]
    old, new, shadow_report = reports
    reasons = []
    shadow_difference = None
    if champion_shadow is None:
        reasons.append("contemporaneous_champion_shadow_required")
    else:
        if (champion_shadow.model_fingerprint != champion.model_fingerprint
                or champion_shadow.domain != shadow.domain or champion_shadow.phase != shadow.phase
                or champion_shadow.dataset_fingerprint != shadow.dataset_fingerprint
                or tuple(p.at for p in champion_shadow.points) != tuple(p.at for p in shadow.points)):
            raise ValueError("paired champion shadow identity or timestamps mismatch")
        if (champion_shadow.synthetic or instant(champion_shadow.captured_until) > now
                or instant(champion_shadow.captured_from) > instant(champion_shadow.points[0].at)
                or instant(champion_shadow.captured_until) < instant(champion_shadow.points[-1].at)):
            reasons.append("champion_shadow_provenance_or_capture_invalid")
        comparison = champion_shadow.report()
        if (shadow_report["total_return"] <= comparison["total_return"]
                or shadow_report["maximum_drawdown"] > comparison["maximum_drawdown"]):
            reasons.append("shadow_return_or_drawdown_not_better")
        try:
            shadow_difference = paired_improvement(comparison["daily_returns"], shadow_report["daily_returns"], policy.bootstrap)
            if shadow_difference["lower"] <= policy.min_ev_improvement:
                reasons.append("shadow_paired_superiority_not_established")
        except ValueError:
            reasons.append("shadow_insufficient_dependent_blocks")
    if any(e.synthetic for e in (champion, challenger, shadow)):
        reasons.append("synthetic_evidence_cannot_promote_operating_models")
    if (instant(shadow.captured_until) - instant(shadow.captured_from)).total_seconds() < policy.min_days * 86400:
        reasons.append("insufficient_actual_elapsed_shadow_capture")
    if instant(shadow.captured_from) > instant(shadow.points[0].at) or instant(shadow.captured_until) < instant(shadow.points[-1].at):
        reasons.append("shadow_prices_outside_capture_interval")
    # A long claimed date range with one/two samples is not elapsed evidence.
    required_closes = max(21, int(policy.min_days * 5 / 7)) if shadow.domain == "us_stock" else policy.min_days
    max_gap = timedelta(hours=96 if shadow.domain == "us_stock" else 36)
    if len(shadow_report["daily_closes"]) < required_closes or any(
            instant(b.at) - instant(a.at) > max_gap for a, b in zip(shadow.points, shadow.points[1:])):
        reasons.append("shadow_capture_coverage_gap")
    for tag, evidence, report in (("oos", challenger, new), ("shadow", shadow, shadow_report)):
        if report["number_of_trades"] < policy.min_trades:
            reasons.append(tag + "_insufficient_closed_trades")
        if report["maximum_drawdown"] > policy.max_drawdown:
            reasons.append(tag + "_drawdown_limit")
        if report["expected_value_per_trade"] is None or report["expected_value_per_trade"] <= 0 or report["total_return"] <= 0:
            reasons.append(tag + "_nonpositive_net_performance")
        if evidence.brier > policy.max_brier or evidence.ece > policy.max_ece:
            reasons.append(tag + "_calibration_failed")
        if evidence.stress_net_return <= 0 or evidence.positive_walk_forward_fraction < .6:
            reasons.append(tag + "_cost_or_walk_forward_failure")
        regimes = {key: item for key, item in report["regime_performance"].items() if key != "unknown" and item["number_of_trades"] >= policy.min_regime_trades}
        if len(regimes) < policy.min_regimes or any(item["expected_value_per_trade"] <= 0 for item in regimes.values()):
            reasons.append(tag + "_regime_stability_not_established")
    for metric in ("sharpe_ratio", "sortino_ratio", "calmar_ratio", "profit_factor", "win_rate"):
        if new[metric] is None or old[metric] is None or new[metric] < old[metric]:
            reasons.append("no_noninferiority_" + metric)
    if new["maximum_drawdown"] > old["maximum_drawdown"] or new["total_return"] <= old["total_return"]:
        reasons.append("return_or_drawdown_not_better")
    if new["turnover"] > old["turnover"] * policy.max_turnover_ratio:
        reasons.append("turnover_budget_exceeded")
    difference = None
    try:
        difference = paired_improvement(old["daily_returns"], new["daily_returns"], policy.bootstrap)
        positive = mean_interval(new["daily_returns"], policy.bootstrap)
        shadow_positive = mean_interval(shadow_report["daily_returns"], policy.bootstrap)
        if difference["lower"] <= policy.min_ev_improvement or positive["lower"] <= 0 or shadow_positive["lower"] <= 0:
            reasons.append("statistical_superiority_not_established")
    except ValueError:
        reasons.append("insufficient_dependent_blocks")
    body = {"domain": challenger.domain, "champion": champion.model_fingerprint,
            "challenger": challenger.model_fingerprint, "approved": not reasons, "reasons": reasons,
            "paired_daily_return_improvement": difference, "policy": asdict(policy),
            "paired_shadow_improvement": shadow_difference,
            "evidence_fingerprints": [fingerprint(asdict(e)) for e in (champion, challenger, shadow, champion_shadow) if e is not None],
            "evaluated_at": now.isoformat(), "paper_only": True, "execution_authority": False}
    return {**body, "fingerprint": fingerprint(body)}


class PaperPromotionStore:
    """Automatic PAPER decisions are CAS-protected and cannot clear risk state."""
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        with connect(path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS adaptive_promotions(seq INTEGER PRIMARY KEY, domain TEXT NOT NULL, champion TEXT NOT NULL, decision TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS adaptive_promotion_policies(domain TEXT PRIMARY KEY, policy TEXT NOT NULL)")
            for action in ("UPDATE", "DELETE"):
                db.execute(f"CREATE TRIGGER IF NOT EXISTS adaptive_promotions_no_{action} BEFORE {action} ON adaptive_promotions BEGIN SELECT RAISE(ABORT,'append-only promotion'); END")
                db.execute(f"CREATE TRIGGER IF NOT EXISTS adaptive_policies_no_{action} BEFORE {action} ON adaptive_promotion_policies BEGIN SELECT RAISE(ABORT,'immutable promotion policy'); END")

    def initialize(self, asset_domain, model_fingerprint, policy=PromotionPolicy()):
        domain(asset_domain)
        digest(model_fingerprint)
        with connect(self.path) as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM adaptive_promotions WHERE domain=?", (asset_domain,)).fetchone():
                raise ValueError("champion already initialized")
            db.execute("INSERT INTO adaptive_promotions(domain,champion,decision) VALUES(?,?,?)",
                       (asset_domain, model_fingerprint, canonical({"action": "explicit_paper_seed"})))
            db.execute("INSERT INTO adaptive_promotion_policies VALUES(?,?)", (asset_domain, canonical(asdict(policy))))

    def current(self, asset_domain):
        domain(asset_domain)
        with connect(self.path) as db:
            row = db.execute("SELECT champion FROM adaptive_promotions WHERE domain=? ORDER BY seq DESC LIMIT 1", (asset_domain,)).fetchone()
            return row[0] if row else None

    def compare_and_promote(self, champion, challenger, shadow, *, now, policy=PromotionPolicy(), champion_shadow=None):
        with connect(self.path) as db:
            locked = db.execute("SELECT policy FROM adaptive_promotion_policies WHERE domain=?", (champion.domain,)).fetchone()
            if locked is None or locked[0] != canonical(asdict(policy)):
                raise ValueError("promotion failure criteria are immutable; new cohort/experiment required")
        decision = evaluate_promotion(champion, challenger, shadow, now=now, policy=policy, champion_shadow=champion_shadow)
        if decision["approved"]:
            with connect(self.path) as db:
                db.execute("BEGIN IMMEDIATE")
                current = db.execute("SELECT champion FROM adaptive_promotions WHERE domain=? ORDER BY seq DESC LIMIT 1", (champion.domain,)).fetchone()
                if current is None or current[0] != champion.model_fingerprint:
                    raise ValueError("champion changed during validation; stale promotion rejected")
                db.execute("INSERT INTO adaptive_promotions(domain,champion,decision) VALUES(?,?,?)",
                           (champion.domain, challenger.model_fingerprint, canonical(decision)))
        return decision
