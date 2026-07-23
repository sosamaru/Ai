"""Deterministic, broker-neutral PAPER execution-cost simulation.

This module never submits orders.  It converts a hypothetical order and a
market snapshot into immutable research evidence suitable for backtests and
PAPER evaluation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from math import sqrt
from typing import Literal

Side = Literal["BUY", "SELL"]
Domain = Literal["crypto", "us_stocks"]
Status = Literal["FILLED", "PARTIAL", "REJECTED"]


@dataclass(frozen=True)
class ExecutionRequest:
    domain: Domain
    symbol: str
    side: Side
    quantity: Decimal
    reference_price: Decimal
    fee_rate: Decimal
    spread_bps: Decimal
    base_slippage_bps: Decimal
    latency_ms: int
    volatility_bps_per_sqrt_second: Decimal
    visible_depth_notional: Decimal
    max_participation_rate: Decimal = Decimal("0.10")
    impact_coefficient_bps: Decimal = Decimal("25")
    provider_available: bool = True


@dataclass(frozen=True)
class ExecutionResult:
    status: Status
    filled_quantity: Decimal
    unfilled_quantity: Decimal
    fill_ratio: Decimal
    execution_price: Decimal | None
    gross_notional: Decimal
    fee_cost: Decimal
    spread_cost: Decimal
    slippage_cost: Decimal
    latency_cost: Decimal
    market_impact_cost: Decimal
    total_cost: Decimal
    effective_cost_bps: Decimal
    reason: str
    fingerprint: str


def _decimal(value: object, name: str) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{name} must be a finite decimal") from exc
    if not result.is_finite():
        raise ValueError(f"{name} must be finite")
    return result


def _validate(request: ExecutionRequest) -> None:
    if request.domain not in ("crypto", "us_stocks"):
        raise ValueError("domain must be crypto or us_stocks")
    if not request.symbol or request.symbol.strip() != request.symbol:
        raise ValueError("symbol must be a non-empty normalized string")
    if request.side not in ("BUY", "SELL"):
        raise ValueError("side must be BUY or SELL")

    positive = {
        "quantity": request.quantity,
        "reference_price": request.reference_price,
        "visible_depth_notional": request.visible_depth_notional,
    }
    non_negative = {
        "fee_rate": request.fee_rate,
        "spread_bps": request.spread_bps,
        "base_slippage_bps": request.base_slippage_bps,
        "volatility_bps_per_sqrt_second": request.volatility_bps_per_sqrt_second,
        "impact_coefficient_bps": request.impact_coefficient_bps,
    }
    for name, value in positive.items():
        value = _decimal(value, name)
        if value <= 0:
            raise ValueError(f"{name} must be positive")
    for name, value in non_negative.items():
        value = _decimal(value, name)
        if value < 0:
            raise ValueError(f"{name} must be non-negative")
    if request.latency_ms < 0:
        raise ValueError("latency_ms must be non-negative")
    if not Decimal("0") < request.max_participation_rate <= Decimal("1"):
        raise ValueError("max_participation_rate must be in (0, 1]")


def _fingerprint(payload: dict[str, object]) -> str:
    normalized = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256(normalized.encode("utf-8")).hexdigest()


def simulate_execution(request: ExecutionRequest) -> ExecutionResult:
    """Simulate one hypothetical PAPER order deterministically.

    The model combines fee, half-spread, configured slippage, adverse latency,
    square-root market impact, liquidity participation, partial fills, and
    provider outages.  Costs are always expressed as positive amounts.
    """

    _validate(request)
    order_notional = request.quantity * request.reference_price

    if not request.provider_available:
        payload = {"request": asdict(request), "status": "REJECTED", "reason": "provider_unavailable"}
        return ExecutionResult(
            status="REJECTED",
            filled_quantity=Decimal("0"),
            unfilled_quantity=request.quantity,
            fill_ratio=Decimal("0"),
            execution_price=None,
            gross_notional=Decimal("0"),
            fee_cost=Decimal("0"),
            spread_cost=Decimal("0"),
            slippage_cost=Decimal("0"),
            latency_cost=Decimal("0"),
            market_impact_cost=Decimal("0"),
            total_cost=Decimal("0"),
            effective_cost_bps=Decimal("0"),
            reason="provider_unavailable",
            fingerprint=_fingerprint(payload),
        )

    executable_notional = request.visible_depth_notional * request.max_participation_rate
    fill_ratio = min(Decimal("1"), executable_notional / order_notional)
    filled_quantity = request.quantity * fill_ratio
    unfilled_quantity = request.quantity - filled_quantity
    gross_notional = filled_quantity * request.reference_price

    participation = gross_notional / request.visible_depth_notional
    impact_bps = request.impact_coefficient_bps * _decimal(sqrt(float(participation)), "impact")
    latency_seconds = Decimal(request.latency_ms) / Decimal("1000")
    latency_bps = request.volatility_bps_per_sqrt_second * _decimal(
        sqrt(float(latency_seconds)), "latency"
    )
    spread_bps = request.spread_bps / Decimal("2")
    total_price_bps = spread_bps + request.base_slippage_bps + latency_bps + impact_bps
    adverse_multiplier = Decimal("1") + total_price_bps / Decimal("10000")
    if request.side == "BUY":
        execution_price = request.reference_price * adverse_multiplier
    else:
        execution_price = request.reference_price * (Decimal("2") - adverse_multiplier)
        if execution_price <= 0:
            raise ValueError("simulated SELL execution price is non-positive")

    fee_cost = gross_notional * request.fee_rate
    spread_cost = gross_notional * spread_bps / Decimal("10000")
    slippage_cost = gross_notional * request.base_slippage_bps / Decimal("10000")
    latency_cost = gross_notional * latency_bps / Decimal("10000")
    market_impact_cost = gross_notional * impact_bps / Decimal("10000")
    total_cost = fee_cost + spread_cost + slippage_cost + latency_cost + market_impact_cost
    effective_cost_bps = total_cost / gross_notional * Decimal("10000")
    status: Status = "FILLED" if fill_ratio == Decimal("1") else "PARTIAL"
    reason = "fully_filled" if status == "FILLED" else "liquidity_limited_partial_fill"

    payload = {
        "request": asdict(request),
        "status": status,
        "filled_quantity": filled_quantity,
        "execution_price": execution_price,
        "total_cost": total_cost,
        "reason": reason,
    }
    return ExecutionResult(
        status=status,
        filled_quantity=filled_quantity,
        unfilled_quantity=unfilled_quantity,
        fill_ratio=fill_ratio,
        execution_price=execution_price,
        gross_notional=gross_notional,
        fee_cost=fee_cost,
        spread_cost=spread_cost,
        slippage_cost=slippage_cost,
        latency_cost=latency_cost,
        market_impact_cost=market_impact_cost,
        total_cost=total_cost,
        effective_cost_bps=effective_cost_bps,
        reason=reason,
        fingerprint=_fingerprint(payload),
    )
