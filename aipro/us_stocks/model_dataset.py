"""Build disjoint, executable-quote markout labels from archived US frames.

These labels are predictive research targets, not realized strategy P&L. No
missing endpoint is interpolated, no external observations are downloaded, and
the short rule gate is applied using only each candidate's current frame.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timedelta
from decimal import Decimal
from hashlib import sha256
import json
import math
import re
from typing import Iterable

from aipro.intelligence.classical_ml import ModelDomain
from aipro.research.purged_training_runner import TrainingRow
from aipro.us_stocks.model_features import FEATURE_NAMES, FEATURE_SCHEMA, model_features
from aipro.us_stocks.portfolio_market import MarketFrame, Quote, instant
from aipro.us_stocks.portfolio_policy import PortfolioPolicy
from aipro.us_stocks.portfolio_strategy import entry_decision


def fingerprint(payload: object) -> str:
    return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


@dataclass(frozen=True)
class ModelSample:
    as_of_utc: str
    label_end_utc: str
    values: tuple[float, ...]
    gross_return_bps: float
    feature_fingerprint: str

    def __post_init__(self) -> None:
        if instant(self.label_end_utc) <= instant(self.as_of_utc):
            raise ValueError("label endpoint must follow the prediction")
        if len(self.values) != len(FEATURE_NAMES) or any(not math.isfinite(v) for v in self.values):
            raise ValueError("model feature schema mismatch")
        if not math.isfinite(self.gross_return_bps) or not -10_000 < self.gross_return_bps <= 10_000:
            raise ValueError("unsupported markout range; inspect corporate actions or bad data")
        if not re.fullmatch("[a-f0-9]{64}", self.feature_fingerprint):
            raise ValueError("sample lineage is required")

    def training_row(self) -> TrainingRow:
        # Absolute microseconds put features and outcome availability on one axis.
        start = int(instant(self.as_of_utc).timestamp() * 1_000_000)
        end = int(instant(self.label_end_utc).timestamp() * 1_000_000)
        return TrainingRow(start, start, end, ModelDomain.US_STOCK, self.values,
                           int(self.gross_return_bps > 0), self.gross_return_bps)


@dataclass(frozen=True)
class ModelDataset:
    symbol: str
    horizon_seconds: int
    synthetic: bool
    policy_fingerprint: str
    source_fingerprint: str
    samples: tuple[ModelSample, ...]
    frame_count: int
    skipped_endpoints: int = 0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9.\-]{0,14}", self.symbol):
            raise ValueError("normalized US symbol required")
        if type(self.horizon_seconds) is not int or not 60 <= self.horizon_seconds <= 3600:
            raise ValueError("horizon must be 60 to 3600 seconds")
        if type(self.synthetic) is not bool or not 1 <= len(self.samples) <= 5000:
            raise ValueError("boolean provenance and 1 to 5000 samples required")
        if type(self.frame_count) is not int or not 2 * len(self.samples) <= self.frame_count <= 100_000:
            raise ValueError("invalid source frame count")
        if type(self.skipped_endpoints) is not int or not 0 <= self.skipped_endpoints <= self.frame_count:
            raise ValueError("invalid skipped endpoint count")
        for value in (self.policy_fingerprint, self.source_fingerprint):
            if not re.fullmatch("[a-f0-9]{64}", value):
                raise ValueError("dataset lineage is required")
        previous = None
        for sample in self.samples:
            start, end = instant(sample.as_of_utc), instant(sample.label_end_utc)
            if end - start != timedelta(seconds=self.horizon_seconds):
                raise ValueError("inconsistent target horizon")
            if previous is not None and start <= previous:
                raise ValueError("samples must have chronological non-overlapping labels")
            previous = end

    @property
    def fingerprint(self) -> str:
        return fingerprint({"schema": FEATURE_SCHEMA, "features": FEATURE_NAMES, **asdict(self)})


def _valid_quote(frame: MarketFrame, symbol: str, policy: PortfolioPolicy) -> Quote | None:
    now = instant(frame.as_of_utc)
    if not instant(frame.session_open_utc) <= now < instant(frame.session_close_utc):
        return None
    if not 0 <= (now - instant(frame.fx_as_of_utc)).total_seconds() <= 300:
        return None
    quote = next((q for q in frame.quotes if q.symbol == symbol), None)
    if (quote is None or not quote.tradable or min(quote.bid_size, quote.ask_size) <= 0
            or not 0 <= (now - instant(quote.as_of_utc)).total_seconds() <= policy.quote_max_age_seconds):
        return None
    return quote


def build_model_dataset(frames: Iterable[MarketFrame], *, symbol: str,
                        horizon_seconds: int = 300, policy: PortfolioPolicy | None = None) -> ModelDataset:
    if type(horizon_seconds) is not int or not 60 <= horizon_seconds <= 3600:
        raise ValueError("horizon must be 60 to 3600 seconds")
    p = policy or PortfolioPolicy()
    samples, previous, pending, synthetic = [], None, None, None
    count, skipped = 0, 0
    source = sha256()
    for frame in frames:
        count += 1
        if count > 100_000:
            raise ValueError("training input exceeds 100,000 frames")
        now = instant(frame.as_of_utc)
        if previous is not None and now <= previous:
            raise ValueError("training frames must be strictly chronological")
        if synthetic is not None and synthetic != frame.synthetic:
            raise ValueError("synthetic and real observations cannot be mixed")
        previous, synthetic = now, frame.synthetic
        source.update(frame.fingerprint.encode())
        quote = _valid_quote(frame, symbol, p)
        if pending is not None:
            target, origin, values, feature_fp, entry_value, session = pending
            if now < target:
                continue
            if now == target and quote is not None and instant(frame.session_open_utc) == session:
                gross = float((quote.bid * frame.usd_krw / entry_value - 1) * 10000)
                samples.append(ModelSample(origin.isoformat(), now.isoformat(), values, gross, feature_fp))
                if len(samples) > 5000:
                    raise ValueError("training input exceeds 5000 disjoint samples")
            else:
                skipped += 1
            pending = None
            # Adjacent labels must not reuse the endpoint as the next entry.
            continue
        if quote is None or quote.spread_bps > p.max_spread_bps:
            continue
        target = now + timedelta(seconds=horizon_seconds)
        if target >= instant(frame.session_close_utc) - timedelta(seconds=p.flatten_before_close_seconds):
            continue
        if not entry_decision("short", quote, frame, p, Decimal(200000)).allowed:
            continue
        values, feature_fp = model_features(quote, now)
        pending = (target, now, values, feature_fp, quote.ask * frame.usd_krw, instant(frame.session_open_utc))
    if pending is not None:
        skipped += 1
    return ModelDataset(symbol, horizon_seconds, bool(synthetic), p.fingerprint,
                        source.hexdigest(), tuple(samples), count, skipped)
