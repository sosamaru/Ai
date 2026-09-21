"""Interpretable baseline strategies plus optional existing research forecasts.

The default rules are untrained hypotheses. A rule score is not a probability.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from statistics import fmean, pstdev
from aipro.intelligence.adaptive_ensemble import adaptive_regime
from typing import Protocol

from aipro.intelligence.domain_regime import Domain, Regime, RegimeFeatures, StrategyCandidate, classify_regime
from aipro.intelligence.market_features import MarketFeaturePolicy, build_market_feature_snapshot
from aipro.intelligence.paper_strategy_validation import ForecastEvidence, PaperMarketSnapshot, validate_paper_strategy
from aipro.intelligence.risk_adjusted_sizing import PaperSizingPolicy
from aipro.us_stocks.portfolio_market import MarketFrame, Quote, instant
from aipro.us_stocks.portfolio_policy import PortfolioPolicy


class ForecastProvider(Protocol):
    """Research inference only; no execution credentials are passed here."""
    def forecast(self, quote: Quote, feature_fingerprint: str) -> ForecastEvidence | None: ...


@dataclass(frozen=True, slots=True)
class EntryDecision:
    allowed: bool
    reason: str
    score: float = 0.0
    feature_fingerprint: str = ""
    notional_cap_krw: Decimal | None = None
    model_id: str = "untrained-rule-baseline"
    regime: str = "unknown"
    probability: float | None = None
    net_ev: float | None = None
    horizon_seconds: int | None = None


def entry_decision(sleeve: str, quote: Quote, frame: MarketFrame, policy: PortfolioPolicy,
                   equity: Decimal, forecaster: ForecastProvider | None = None) -> EntryDecision:
    info = quote.intelligence
    if info is None:
        return EntryDecision(False, "missing_news_macro_filing_context")
    age = (instant(frame.as_of_utc) - instant(info.as_of_utc)).total_seconds()
    if not 0 <= age <= policy.intelligence_max_age_seconds:
        return EntryDecision(False, "stale_or_future_intelligence")
    if info.material_risk or info.macro_risk_off or info.news_sentiment < -0.25:
        return EntryDecision(False, "news_macro_or_filing_risk")
    if quote.daily_dollar_volume < policy.minimum_daily_dollar_volume:
        return EntryDecision(False, "insufficient_liquidity")
    if sleeve == "long":
        bars = quote.daily_bars
        if len(bars) < 200:
            return EntryDecision(False, "long_requires_200_completed_daily_bars")
        if instant(bars[-1].timestamp_utc).date() >= instant(frame.session_open_utc).date():
            return EntryDecision(False, "long_requires_previous_completed_session")
        if instant(frame.as_of_utc) - instant(bars[-1].timestamp_utc) > timedelta(days=5):
            return EntryDecision(False, "stale_daily_history")
        if len({instant(bar.timestamp_utc).date() for bar in bars}) != len(bars):
            return EntryDecision(False, "multiple_bars_in_one_daily_session")
        closes = [bar.close for bar in bars]
        fast, slow = fmean(closes[-50:]), fmean(closes[-200:])
        if not float(quote.mid) > fast > slow:
            return EntryDecision(False, "long_trend_not_positive")
        if float(quote.mid) > fast * 1.20:
            return EntryDecision(False, "long_price_overextended")
        return EntryDecision(True, "long_50_200_trend", fast / slow - 1, regime="weak_bull")

    bars = quote.intraday_bars
    if len(bars) < 30:
        return EntryDecision(False, "short_requires_30_completed_bars")
    if any(not instant(frame.session_open_utc) <= instant(bar.timestamp_utc) < instant(frame.as_of_utc)
           for bar in bars):
        return EntryDecision(False, "intraday_bars_must_precede_execution_in_this_session")
    features = build_market_feature_snapshot(quote.symbol, bars, as_of_utc=frame.as_of_utc,
        policy=MarketFeaturePolicy(maximum_age_seconds=120))
    if not features.eligible:
        return EntryDecision(False, ",".join(features.ineligible_reasons))
    total_volume = sum(bar.volume for bar in bars)
    if total_volume <= 0:
        return EntryDecision(False, "no_volume")
    vwap = sum((bar.high + bar.low + bar.close) / 3 * bar.volume for bar in bars) / total_volume
    returns = [b.close / a.close - 1 for a, b in zip(bars, bars[1:])]
    rolling_vols = [pstdev(returns[i:i + 5]) for i in range(max(0, len(returns) - 9))]
    vol_scale = pstdev(rolling_vols) if rolling_vols else 0
    vol_z = (pstdev(returns[-5:]) - fmean(rolling_vols)) / vol_scale if vol_scale > 1e-12 else 0
    breadth = [1 if float(q.mid) > q.intraday_bars[0].close else -1 for q in frame.quotes if q.intraday_bars]
    regime_features = RegimeFeatures(
        domain=Domain.US_STOCK, trend_return=features.return_medium_pct / 100,
        realized_volatility=features.realized_volatility_pct / 100, volatility_zscore=vol_z,
        drawdown=min(0.0, float(quote.mid) / max(bar.high for bar in bars) - 1),
        breadth=fmean(breadth) if breadth else 0.0, momentum=min(0.79, max(-1.0, features.trend_score)),
        liquidity_stress=min(1.0, float(quote.spread_bps / max(policy.max_spread_bps, 1)) / 3),
    )
    regime = classify_regime(regime_features)
    detailed_regime = adaptive_regime(regime_features).value
    if (regime.regime not in {Regime.TREND_UP, Regime.RANGE}
            or features.volume_ratio < 1.5 or features.return_short_pct <= 0
            or features.return_medium_pct > 8 or features.average_true_range_pct > 5
            or float(quote.mid) <= max(bar.high for bar in bars[-21:-1])
            or float(quote.mid) <= vwap):
        return EntryDecision(False, "momentum_breakout_volume_or_regime_gate", feature_fingerprint=features.fingerprint)
    score = features.volume_ratio + features.return_short_pct + info.news_sentiment * 0.25
    if forecaster is None:
        return EntryDecision(True, "short_breakout_vwap_volume", score, features.fingerprint, regime=detailed_regime)
    try:
        frame_forecast = getattr(forecaster, "forecast_frame", None)
        forecast = (frame_forecast(quote, frame, policy, features.fingerprint) if callable(frame_forecast)
                    else forecaster.forecast(quote, features.fingerprint))
        if forecast is not None and not isinstance(forecast, ForecastEvidence):
            raise ValueError("invalid forecast result")
    except Exception as exc:
        # An advisory model outage must not roll back exits already required by
        # portfolio risk controls. Never expose arbitrary model exception text.
        return EntryDecision(False, "forecast_error:" + type(exc).__name__)
    if forecast is None:
        return EntryDecision(False, getattr(forecaster, "last_reason", "forecast_missing_or_lineage_mismatch"))
    if forecast.feature_fingerprint != features.fingerprint:
        return EntryDecision(False, "forecast_missing_or_lineage_mismatch")
    try:
        from dataclasses import replace
        return replace(_forecast_entry(forecast, quote, frame, policy, equity, regime_features, features, score), regime=detailed_regime)
    except Exception as exc:
        return EntryDecision(False, "forecast_error:" + type(exc).__name__)


def _forecast_entry(forecast, quote, frame, policy, equity, regime_features, features, score) -> EntryDecision:
    if not forecast.probability_calibrated:
        return EntryDecision(False, "uncalibrated_probability_cannot_size_position", model_id=forecast.model_id)
    validation = validate_paper_strategy(
        domain=Domain.US_STOCK, features=regime_features,
        candidates=(StrategyCandidate("short_momentum", frozenset({Domain.US_STOCK}),
            frozenset({Regime.TREND_UP, Regime.RANGE}),
            forecast.win_probability * forecast.expected_gain_pct - (1 - forecast.win_probability) * forecast.expected_loss_pct,
            forecast.uncertainty),), forecast=forecast,
        market=PaperMarketSnapshot(symbol=quote.symbol, equity=equity, unit_price=quote.ask * frame.usd_krw,
            stop_distance_pct=float(policy.short_stop), forecast_volatility_pct=max(0.001, features.realized_volatility_pct / 100),
            fee_rate=policy.fee_rate + policy.fx_cost_rate, spread_bps=quote.spread_bps,
            base_slippage_bps=policy.slippage_rate * 10000, latency_ms=0, volatility_bps_per_sqrt_second=Decimal(0),
            visible_depth_notional=quote.ask_size * quote.ask * frame.usd_krw),
        sizing_policy=PaperSizingPolicy(risk_budget_pct=float(policy.short_risk_per_trade),
            max_position_pct=float(policy.short_position_fraction)),
    )
    cap = validation.sizing.suggested_notional if validation.sizing else Decimal(0)
    net_ev = None
    if validation.sizing and validation.execution:
        net_ev = validation.sizing.expected_value.net_ev_pct - float(validation.execution.effective_cost_bps) * 2 / 10000
    return EntryDecision(validation.eligible, validation.reason, score, features.fingerprint, cap, forecast.model_id,
                         probability=forecast.win_probability, net_ev=net_ev, horizon_seconds=forecast.horizon_seconds)
