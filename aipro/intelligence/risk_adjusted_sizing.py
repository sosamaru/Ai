"""Risk-adjusted expected value and volatility-based PAPER sizing."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from typing import Mapping


class SizingValidationError(ValueError):
    """Raised when a sizing request is malformed or unsafe."""


@dataclass(frozen=True)
class ExpectedValueEstimate:
    win_probability: float
    expected_gain_pct: float
    loss_probability: float
    expected_loss_pct: float
    estimated_cost_pct: float
    gross_ev_pct: float
    net_ev_pct: float
    payoff_ratio: float
    fractional_kelly: float


@dataclass(frozen=True)
class PaperSizingPolicy:
    risk_budget_pct: float = 0.005
    target_volatility_pct: float = 0.01
    max_position_pct: float = 0.10
    max_fractional_kelly: float = 0.25
    min_net_ev_pct: float = 0.0
    uncertainty_haircut: float = 0.50


@dataclass(frozen=True)
class PaperSizingDecision:
    eligible: bool
    reason: str
    domain: str
    symbol: str
    equity: Decimal
    unit_price: Decimal
    stop_distance_pct: float
    forecast_volatility_pct: float
    uncertainty: float
    expected_value: ExpectedValueEstimate
    risk_budget_amount: Decimal
    suggested_notional: Decimal
    suggested_quantity: Decimal
    capped_position_pct: float
    fingerprint: str


def _finite(name: str, value: float, minimum: float | None = None, maximum: float | None = None) -> float:
    result = float(value)
    if not math.isfinite(result):
        raise SizingValidationError(f"{name} must be finite")
    if minimum is not None and result < minimum:
        raise SizingValidationError(f"{name} must be >= {minimum}")
    if maximum is not None and result > maximum:
        raise SizingValidationError(f"{name} must be <= {maximum}")
    return result


def _money(name: str, value: Decimal | str | int | float) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise SizingValidationError(f"{name} must be decimal-compatible") from exc
    if not result.is_finite() or result <= 0:
        raise SizingValidationError(f"{name} must be finite and positive")
    return result


def estimate_expected_value(*, win_probability: float, expected_gain_pct: float,
                            expected_loss_pct: float, estimated_cost_pct: float = 0.0,
                            max_fractional_kelly: float = 0.25) -> ExpectedValueEstimate:
    p = _finite("win_probability", win_probability, 0.0, 1.0)
    gain = _finite("expected_gain_pct", expected_gain_pct, 0.0)
    loss = _finite("expected_loss_pct", expected_loss_pct, 0.0)
    cost = _finite("estimated_cost_pct", estimated_cost_pct, 0.0)
    kelly_cap = _finite("max_fractional_kelly", max_fractional_kelly, 0.0, 1.0)
    if loss == 0.0:
        raise SizingValidationError("expected_loss_pct must be greater than zero")
    q = 1.0 - p
    gross_ev = p * gain - q * loss
    net_ev = gross_ev - cost
    payoff_ratio = gain / loss
    full_kelly = (payoff_ratio * p - q) / payoff_ratio if payoff_ratio > 0 else 0.0
    fractional_kelly = min(max(full_kelly, 0.0), kelly_cap)
    return ExpectedValueEstimate(p, gain, q, loss, cost, gross_ev, net_ev, payoff_ratio, fractional_kelly)


def size_paper_position(*, domain: str, symbol: str,
                        equity: Decimal | str | int | float,
                        unit_price: Decimal | str | int | float,
                        stop_distance_pct: float,
                        forecast_volatility_pct: float,
                        uncertainty: float,
                        win_probability: float,
                        expected_gain_pct: float,
                        expected_loss_pct: float,
                        estimated_cost_pct: float = 0.0,
                        policy: PaperSizingPolicy = PaperSizingPolicy(),
                        metadata: Mapping[str, str] | None = None) -> PaperSizingDecision:
    normalized_domain = domain.strip().lower()
    if normalized_domain not in {"crypto", "us_stocks"}:
        raise SizingValidationError("domain must be crypto or us_stocks")
    normalized_symbol = symbol.strip().upper()
    if not normalized_symbol:
        raise SizingValidationError("symbol is required")
    account_equity = _money("equity", equity)
    price = _money("unit_price", unit_price)
    stop = _finite("stop_distance_pct", stop_distance_pct, 0.0)
    vol = _finite("forecast_volatility_pct", forecast_volatility_pct, 0.0)
    uncertainty_value = _finite("uncertainty", uncertainty, 0.0, 1.0)
    if stop == 0.0 or vol == 0.0:
        raise SizingValidationError("stop distance and forecast volatility must be greater than zero")

    risk_budget_pct = _finite("risk_budget_pct", policy.risk_budget_pct, 0.0, 1.0)
    target_vol = _finite("target_volatility_pct", policy.target_volatility_pct, 0.0)
    max_position_pct = _finite("max_position_pct", policy.max_position_pct, 0.0, 1.0)
    min_ev = _finite("min_net_ev_pct", policy.min_net_ev_pct)
    uncertainty_haircut = _finite("uncertainty_haircut", policy.uncertainty_haircut, 0.0, 1.0)
    if risk_budget_pct == 0.0 or target_vol == 0.0 or max_position_pct == 0.0:
        raise SizingValidationError("policy budgets and caps must be greater than zero")

    ev = estimate_expected_value(
        win_probability=win_probability,
        expected_gain_pct=expected_gain_pct,
        expected_loss_pct=expected_loss_pct,
        estimated_cost_pct=estimated_cost_pct,
        max_fractional_kelly=policy.max_fractional_kelly,
    )
    risk_budget_amount = account_equity * Decimal(str(risk_budget_pct))
    eligible = ev.net_ev_pct > min_ev and ev.fractional_kelly > 0.0
    reason = "eligible" if eligible else "non_positive_risk_adjusted_edge"
    notional = Decimal("0")
    quantity = Decimal("0")
    capped_pct = 0.0
    if eligible:
        stop_notional = risk_budget_amount / Decimal(str(stop))
        volatility_multiplier = min(target_vol / vol, 1.0)
        confidence_multiplier = max(0.0, 1.0 - uncertainty_value * uncertainty_haircut)
        kelly_multiplier = ev.fractional_kelly / policy.max_fractional_kelly if policy.max_fractional_kelly > 0 else 0.0
        raw_notional = stop_notional * Decimal(str(volatility_multiplier * confidence_multiplier * kelly_multiplier))
        hard_cap = account_equity * Decimal(str(max_position_pct))
        notional = min(raw_notional, hard_cap).quantize(Decimal("0.00000001"))
        quantity = (notional / price).quantize(Decimal("0.00000001"))
        capped_pct = float(notional / account_equity)

    payload = {
        "domain": normalized_domain, "symbol": normalized_symbol,
        "equity": str(account_equity), "unit_price": str(price),
        "stop_distance_pct": stop, "forecast_volatility_pct": vol,
        "uncertainty": uncertainty_value, "net_ev_pct": ev.net_ev_pct,
        "fractional_kelly": ev.fractional_kelly,
        "risk_budget_amount": str(risk_budget_amount),
        "suggested_notional": str(notional), "suggested_quantity": str(quantity),
        "eligible": eligible, "reason": reason,
        "metadata": dict(sorted((metadata or {}).items())),
    }
    fingerprint = sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return PaperSizingDecision(
        eligible, reason, normalized_domain, normalized_symbol, account_equity, price,
        stop, vol, uncertainty_value, ev, risk_budget_amount, notional, quantity,
        capped_pct, fingerprint,
    )
