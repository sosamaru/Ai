"""Explicitly pinned PAPER ensemble with bounded resolved-shadow adaptation.

Only numeric, validated artifacts enter. Observed executable-quote markouts tune
weights, never core risk or champion promotion. They are not portfolio returns.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import timedelta
import json
from pathlib import Path
from statistics import fmean

from aipro.core.evidence import canonical, digest, fingerprint, instant
from aipro.intelligence.adaptive_ensemble import (
    AdaptiveRegime, EnsemblePolicy, Prediction, adapt_weights, adaptive_regime, bounded_weights, combine,
)
from aipro.intelligence.calibration import reliability_report
from aipro.intelligence.domain_regime import Domain, RegimeFeatures
from aipro.intelligence.paper_strategy_validation import ForecastEvidence
from aipro.sqlite_utils import connect
from aipro.us_stocks.model_artifact import ArtifactForecastProvider, load_artifact
from aipro.us_stocks.model_features import model_features


class EnsembleForecastProvider:
    def __init__(self, providers, *, state_path: Path, allow_synthetic=False, policy=EnsemblePolicy()):
        self.providers = tuple(providers)
        if not 2 <= len(self.providers) <= 6:
            raise ValueError("ensemble requires 2 to 6 distinct qualified models")
        bodies = [p.artifact.payload for p in self.providers]
        if len({p.model_id for p in self.providers}) != len(bodies):
            raise ValueError("duplicate model artifacts")
        for key in ("domain", "symbol", "feature_schema", "policy_fingerprint", "horizon_seconds", "synthetic"):
            if len({b[key] for b in bodies}) != 1:
                raise ValueError("ensemble contract mismatch: " + key)
        if bodies[0]["synthetic"] and not allow_synthetic:
            raise ValueError("synthetic ensemble only allowed in explicit synthetic replay")
        self.policy, self.state_path = policy, state_path
        self.model_id = "ensemble:" + fingerprint({"models": [p.model_id for p in self.providers], "policy": asdict(policy)})
        self.last_reason, self.last_report = "ensemble_not_evaluated", {}
        state_path.parent.mkdir(parents=True, exist_ok=True)
        with connect(state_path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS paper_ensemble_state(id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
            if not db.execute("SELECT 1 FROM paper_ensemble_state WHERE id=?", (self.model_id,)).fetchone():
                initial = {"weights": {}, "observations": {}, "pending": None, "last_at": None, "last_resolution": None}
                db.execute("INSERT INTO paper_ensemble_state VALUES(?,?)", (self.model_id, canonical(initial)))

    def forecast(self, quote, feature_fingerprint):
        return None

    def forecast_frame(self, quote, frame, policy, feature_fingerprint):
        now = instant(frame.as_of_utc)
        values, observed = model_features(quote, now)
        if observed != feature_fingerprint:
            self.last_reason = "ensemble_feature_lineage_mismatch"
            return None
        predictions = []
        for provider in self.providers:
            forecast = provider.forecast_frame(quote, frame, policy, feature_fingerprint, enforce_threshold=False)
            if forecast is None:
                # Failed/stale candidates are never silently given zero weight;
                # renormalization could violate the single-model weight cap.
                self.last_reason = "ensemble_member_unavailable:" + provider.last_reason
                return None
            body = provider.artifact.payload
            gross = forecast.win_probability * forecast.expected_gain_pct - (1 - forecast.win_probability) * forecast.expected_loss_pct
            vol = max(.001, values[2] / 100)
            predictions.append(Prediction(provider.model_id, "us_stock", quote.symbol, now.isoformat(),
                body["horizon_seconds"], observed, gross, forecast.win_probability, forecast.expected_gain_pct,
                forecast.expected_loss_pct, vol, 1 - forecast.uncertainty, forecast.uncertainty,
                min(.99, max(forecast.expected_loss_pct * 3, vol * 3)),
                float(2 * (policy.fee_rate + policy.fx_cost_rate)),
                float(2 * policy.slippage_rate + quote.spread_bps / 10000), tuple(r.value for r in AdaptiveRegime)))
        # These are observable within-symbol features. Market breadth/macro data
        # remain separately validated by entry_decision; none is fabricated here.
        bars = quote.intraday_bars
        regime = adaptive_regime(RegimeFeatures(Domain.US_STOCK, values[1] / 100, max(0, values[2] / 100),
            0.0, min(0.0, float(quote.mid) / max(b.high for b in bars) - 1), 0.0,
            max(-1, min(1, values[6])), min(1, float(quote.spread_bps / max(policy.max_spread_bps, 1)) / 3)))
        with connect(self.state_path) as db:
            db.execute("BEGIN IMMEDIATE")
            state = json.loads(db.execute("SELECT payload FROM paper_ensemble_state WHERE id=?", (self.model_id,)).fetchone()[0])
            if state["last_at"] and now <= instant(state["last_at"]):
                self.last_reason = "ensemble_duplicate_or_reversed_frame"
                return None
            pending = state["pending"]
            resolved = False
            if pending and now >= instant(pending["end"]):
                if now == instant(pending["end"]) and pending["session"] == instant(frame.session_open_utc).isoformat():
                    gross_return = float(quote.bid * frame.usd_krw) / pending["entry"] - 1
                    bucket = state["observations"].setdefault(pending["regime"], [])
                    bucket.append({"net": gross_return - pending["cost"], "label": int(gross_return > 0), "p": pending["p"]})
                    del bucket[:-300]
                    if len(bucket) >= 30:
                        # Expected value of exposure scaled by declared probability,
                        # penalized for proper-scoring loss. These are markout scores.
                        scores = {p.model_id: fmean(row["p"][p.model_id] * row["net"]
                                  - .01 * (row["p"][p.model_id] - row["label"])**2 for row in bucket) for p in predictions}
                        key = pending["regime"]
                        current = state["weights"].get(key) or bounded_weights({p.model_id: 0.0 for p in predictions}, self.policy)
                        state["weights"][key] = adapt_weights(current, scores, observations=len(bucket), policy=self.policy)
                    state["last_resolution"] = now.isoformat()
                    resolved = True
                state["pending"] = None
            weights = state["weights"].setdefault(regime.value, bounded_weights({p.model_id: 0.0 for p in predictions}, self.policy))
            bucket = state["observations"].get(regime.value, [])
            degradation = .5 if len(bucket) >= 30 and fmean(row["net"] for row in bucket) <= 0 else 0.0
            report = combine(predictions, weights, regime=regime, now=now, degradation=degradation, policy=self.policy)
            if bucket:
                report["calibration"] = {p.model_id: reliability_report([row["p"][p.model_id] for row in bucket],
                                               [row["label"] for row in bucket]) for p in predictions}
            report["resolved_shadow_markouts"] = len(bucket)
            report["promotion_authority"] = False
            self.last_report = report
            end = now + timedelta(seconds=predictions[0].horizon_seconds)
            if state["pending"] is None and not resolved and end < instant(frame.session_close_utc):
                state["pending"] = {"end": end.isoformat(), "entry": float(quote.ask * frame.usd_krw),
                    "session": instant(frame.session_open_utc).isoformat(), "regime": regime.value,
                    "cost": float(2 * (policy.fee_rate + policy.fx_cost_rate + policy.slippage_rate)),
                    "p": {p.model_id: p.win_probability for p in predictions}}
            state["last_at"] = now.isoformat()
            db.execute("UPDATE paper_ensemble_state SET payload=? WHERE id=?", (canonical(state), self.model_id))
        if not report.get("allowed"):
            self.last_reason = report.get("reason", "ensemble_EV_or_confidence_gate")
            return None
        self.last_reason = "ensemble_forecast_available"
        # Aggregate win/loss conditional payoffs correctly: averages of conditional
        # gains alone do not preserve the mixture's expected value.
        p = report["win_probability"]
        gain = sum(weights[x.model_id] * x.win_probability * x.expected_gain for x in predictions) / p if p else 0
        loss = sum(weights[x.model_id] * (1 - x.win_probability) * x.expected_loss for x in predictions) / (1 - p) if p < 1 else 0
        return ForecastEvidence(p, gain, loss, report["uncertainty"], self.model_id, observed)


def load_ensemble(path: Path, *, expected_fingerprint: str, state_path: Path):
    digest(expected_fingerprint)
    with path.open("rb") as handle:
        raw = handle.read(100001)
    if len(raw) > 100000:
        raise ValueError("ensemble manifest too large")
    from aipro.us_stocks.model_artifact import _unique_object
    body = json.loads(raw, object_pairs_hook=_unique_object)
    if set(body) != {"schema", "models"} or body["schema"] != "aipro-paper-ensemble-v1" or fingerprint(body) != expected_fingerprint:
        raise ValueError("ensemble manifest schema or pin mismatch")
    if not 2 <= len(body["models"]) <= 6:
        raise ValueError("ensemble candidate count outside bounds")
    providers = []
    for item in body["models"]:
        if set(item) != {"path", "fingerprint"}:
            raise ValueError("invalid ensemble member")
        member = (path.parent / item["path"]).resolve()
        if not member.is_relative_to(path.parent.resolve()):
            raise ValueError("model must be inside the reviewed manifest directory")
        providers.append(ArtifactForecastProvider(load_artifact(member, expected_fingerprint=item["fingerprint"])))
    return EnsembleForecastProvider(providers, state_path=state_path)
