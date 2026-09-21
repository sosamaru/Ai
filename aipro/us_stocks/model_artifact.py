"""Bounded numeric JSON model artifacts; never unpickle executable objects."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import math
import os
from pathlib import Path
import re
import tempfile

from aipro.intelligence.paper_strategy_validation import ForecastEvidence
from aipro.research.purged_training_runner import FittedLogisticModel
from aipro.us_stocks.model_dataset import fingerprint
from aipro.us_stocks.model_features import FEATURE_NAMES, FEATURE_SCHEMA, model_features
from aipro.us_stocks.portfolio_market import MarketFrame, Quote, instant
from aipro.us_stocks.portfolio_policy import PortfolioPolicy

ARTIFACT_SCHEMA = "aipro-us-logistic-paper-v1"
ROBUST_ARTIFACT_SCHEMA = "aipro-us-logistic-paper-v3"


def robust_quality_blockers(evidence: dict) -> list[str]:
    if set(evidence) != {"net_ev_lower_bound", "positive_walk_forward_fraction", "ece", "calibrated"}:
        raise ValueError("invalid robust validation evidence")
    if type(evidence["calibrated"]) is not bool:
        raise ValueError("invalid calibration flag")
    for key in ("net_ev_lower_bound", "positive_walk_forward_fraction", "ece"):
        value = evidence[key]
        if key == "net_ev_lower_bound" and value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("robust evidence must be finite")
        if key != "net_ev_lower_bound" and not 0 <= value <= 1:
            raise ValueError("invalid robust evidence bounds")
    return [reason for failed, reason in (
        (evidence["net_ev_lower_bound"] is None or evidence["net_ev_lower_bound"] <= 0,
         "positive_EV_lower_bound_not_established"),
        (evidence["positive_walk_forward_fraction"] < .6, "walk_forward_majority_not_profitable"),
        (evidence["ece"] > .10, "holdout_ECE_above_ceiling"),
        (not evidence["calibrated"], "separate_probability_calibration_required"),
    ) if failed]


def quality_blockers(validation: dict) -> list[str]:
    """Fixed acceptance contract, shared by training and the runtime loader."""
    keys = {"cv_accepted", "cv_samples", "cv_folds", "holdout_samples", "selected_samples",
            "balanced_accuracy", "brier_score", "prior_brier_score", "net_ev_bps",
            "stress_net_ev_bps", "rule_net_ev_bps"}
    if set(validation) != keys or type(validation["cv_accepted"]) is not bool:
        raise ValueError("invalid validation schema")
    for key in keys - {"cv_accepted"}:
        value = validation[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError("validation metrics must be finite numbers")
    for key in ("cv_samples", "cv_folds", "holdout_samples", "selected_samples"):
        if type(validation[key]) is not int or validation[key] < 0:
            raise ValueError("sample counts must be non-negative integers")
    for key in ("balanced_accuracy", "brier_score", "prior_brier_score"):
        if not 0 <= validation[key] <= 1:
            raise ValueError("invalid classification metric")
    if validation["selected_samples"] > validation["holdout_samples"]:
        raise ValueError("selected samples exceed holdout")
    checks = (
        (not validation["cv_accepted"], "cross_validation_rejected"),
        (validation["cv_samples"] < 300 or validation["cv_folds"] < 3, "insufficient_cv_evidence"),
        (validation["holdout_samples"] < 100, "insufficient_final_holdout"),
        (validation["selected_samples"] < 30, "insufficient_selected_holdout_samples"),
        (validation["balanced_accuracy"] < 0.52, "holdout_accuracy_below_floor"),
        (validation["brier_score"] > 0.25, "holdout_calibration_above_ceiling"),
        (validation["brier_score"] >= validation["prior_brier_score"], "no_brier_improvement_over_training_prior"),
        (validation["net_ev_bps"] <= 0, "nonpositive_holdout_net_ev"),
        (validation["stress_net_ev_bps"] <= 0, "double_cost_stress_failed"),
        (validation["net_ev_bps"] <= validation["rule_net_ev_bps"], "no_markout_improvement_over_rule_baseline"),
    )
    return [reason for failed, reason in checks if failed]


def write_json_atomic(path: Path, value: object) -> None:
    """Same-directory replace: a interrupted write cannot leave half a model."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                         prefix=".aipro-model-", delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


@dataclass(frozen=True)
class ModelArtifact:
    payload: dict
    fingerprint: str
    model: FittedLogisticModel

    @property
    def model_id(self) -> str:
        return "us-logistic:" + self.fingerprint

    def to_dict(self) -> dict:
        return {"artifact": self.payload, "fingerprint": self.fingerprint}


def validate_artifact(document: dict) -> ModelArtifact:
    try:
        if set(document) != {"artifact", "fingerprint"}:
            raise ValueError("invalid model wrapper")
        body = document["artifact"]
        expected_keys = {"schema", "domain", "sleeve", "feature_schema", "feature_names", "symbol", "model",
            "policy_fingerprint", "dataset_fingerprint", "report_fingerprint", "training_end_utc", "validation_end_utc",
            "expires_at_utc", "synthetic", "qualified", "blockers", "validation", "expected_gain_pct",
            "expected_loss_pct", "uncertainty", "decision_threshold", "horizon_seconds", "paper_only", "live_ready"}
        if body.get("schema") in {"aipro-us-logistic-paper-v2", ROBUST_ARTIFACT_SCHEMA}:
            expected_keys.add("calibrator")
        if body.get("schema") == ROBUST_ARTIFACT_SCHEMA:
            expected_keys.add("robustness")
        if set(body) != expected_keys or document["fingerprint"] != fingerprint(body):
            raise ValueError("model schema or fingerprint mismatch")
        if (body["schema"] not in {ARTIFACT_SCHEMA, "aipro-us-logistic-paper-v2", ROBUST_ARTIFACT_SCHEMA} or body["domain"] != "us_stock" or body["sleeve"] != "short"
                or body["feature_schema"] != FEATURE_SCHEMA or body["feature_names"] != list(FEATURE_NAMES)
                or body["paper_only"] is not True or body["live_ready"] is not False):
            raise ValueError("model domain, feature schema or execution boundary mismatch")
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", body["symbol"]):
            raise ValueError("invalid model symbol")
        for key in ("policy_fingerprint", "dataset_fingerprint", "report_fingerprint"):
            if not re.fullmatch("[a-f0-9]{64}", body[key]):
                raise ValueError("model lineage is required")
        if type(body["synthetic"]) is not bool or type(body["qualified"]) is not bool:
            raise ValueError("model evidence flags must be boolean")
        blockers = quality_blockers(body["validation"])
        if body["schema"] == ROBUST_ARTIFACT_SCHEMA:
            blockers += robust_quality_blockers(body["robustness"])
            if body["robustness"]["calibrated"] != (body["calibrator"] is not None):
                raise ValueError("calibrator and validation evidence disagree")
        if body["blockers"] != blockers or body["qualified"] != (not blockers):
            raise ValueError("model qualification disagrees with validation evidence")
        trained, validated, expires = (instant(body[key]) for key in
            ("training_end_utc", "validation_end_utc", "expires_at_utc"))
        max_days = 90 if body["schema"] in {"aipro-us-logistic-paper-v2", ROBUST_ARTIFACT_SCHEMA} else 7
        if not trained < validated < expires or expires - validated > timedelta(days=max_days):
            raise ValueError("invalid model evidence or expiry interval")
        if type(body["horizon_seconds"]) is not int or not 60 <= body["horizon_seconds"] <= 3600:
            raise ValueError("invalid forecast horizon")
        for key in ("expected_gain_pct", "expected_loss_pct", "uncertainty", "decision_threshold"):
            value = body[key]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 < value < 1:
                raise ValueError("invalid forecast parameter")
        parameters = body["model"]
        if set(parameters) != {"weights", "bias", "means", "scales"}:
            raise ValueError("invalid model parameter schema")
        model = FittedLogisticModel(tuple(parameters["weights"]), parameters["bias"],
                                   tuple(parameters["means"]), tuple(parameters["scales"]))
        if len(model.weights) != len(FEATURE_NAMES):
            raise ValueError("model feature width mismatch")
        if body.get("calibrator") is not None:
            from aipro.intelligence.calibration import Calibrator
            Calibrator(**body["calibrator"])
        return ModelArtifact(body, document["fingerprint"], model)
    except (KeyError, TypeError, OverflowError) as exc:
        raise ValueError("malformed numeric model artifact") from None


def load_artifact(path: Path, *, expected_fingerprint: str | None = None) -> ModelArtifact:
    with path.open("rb") as handle:
        raw = handle.read(1_000_001)
    if len(raw) > 1_000_000:
        raise ValueError("model artifact exceeds 1 MB")
    document = json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda value: (_ for _ in ()).throw(ValueError("non-finite JSON number")))
    artifact = validate_artifact(document)
    if expected_fingerprint is not None and artifact.fingerprint != expected_fingerprint:
        raise ValueError("model does not match the explicitly pinned SHA-256")
    return artifact


class ArtifactForecastProvider:
    """Explicitly selected PAPER model; failures abstain, never select a new model."""

    def __init__(self, artifact: ModelArtifact, *, allow_synthetic: bool = False) -> None:
        if not artifact.payload["qualified"]:
            raise ValueError("model has not passed the fixed research acceptance contract")
        if artifact.payload["synthetic"] and not allow_synthetic:
            raise ValueError("synthetic model is restricted to explicit synthetic replay")
        if artifact.payload["schema"] != ROBUST_ARTIFACT_SCHEMA:
            raise ValueError("legacy model lacks enforced robust calibration evidence; retrain before serving")
        self.artifact = artifact
        self.model_id = artifact.model_id
        self.last_reason = "model_not_evaluated"

    def forecast(self, quote: Quote, feature_fingerprint: str) -> ForecastEvidence | None:
        # The canonical runtime supplies the full frame for provenance/time checks.
        self.last_reason = "model_requires_frame_context"
        return None

    def forecast_frame(self, quote: Quote, frame: MarketFrame, policy: PortfolioPolicy,
                       feature_fingerprint: str, *, enforce_threshold: bool = True) -> ForecastEvidence | None:
        body, now = self.artifact.payload, instant(frame.as_of_utc)
        checks = (
            (quote.symbol != body["symbol"], "model_symbol_mismatch"),
            (policy.fingerprint != body["policy_fingerprint"], "model_policy_mismatch"),
            (frame.synthetic != body["synthetic"], "model_provenance_mismatch"),
            (now <= instant(body["validation_end_utc"]), "model_would_see_future_evidence"),
            (now > instant(body["expires_at_utc"]) or now - instant(body["training_end_utc"]) > timedelta(
                days=120 if body["schema"] in {"aipro-us-logistic-paper-v2", ROBUST_ARTIFACT_SCHEMA} else 30), "model_expired"),
        )
        for failed, reason in checks:
            if failed:
                self.last_reason = reason
                return None
        values, observed_fingerprint = model_features(quote, now)
        if observed_fingerprint != feature_fingerprint:
            self.last_reason = "model_feature_lineage_mismatch"
            return None
        if max(abs(value) for value in self.artifact.model.standardized(values)) > 6:
            self.last_reason = "model_feature_out_of_distribution"
            return None
        probability = self.artifact.model.predict(values)
        if "calibrator" in body:
            from aipro.intelligence.calibration import Calibrator
            probability = Calibrator(**body["calibrator"]).predict(probability)
        if enforce_threshold and probability < body["decision_threshold"]:
            self.last_reason = "model_probability_below_threshold"
            return None
        self.last_reason = "model_forecast_available"
        return ForecastEvidence(probability, body["expected_gain_pct"], body["expected_loss_pct"],
                                body["uncertainty"], self.model_id, observed_fingerprint,
                                probability_calibrated=True, horizon_seconds=body["horizon_seconds"])
