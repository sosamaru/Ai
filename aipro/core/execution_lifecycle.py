"""Replayable order state machine; unknown timeout never authorizes a retry."""
from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum

from aipro.core.evidence import domain, finite, instant


class ExecutionState(str, Enum):
    NEW = "NEW"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class OrderLifecycle:
    domain: str
    order_id: str
    quantity: float
    state: ExecutionState = ExecutionState.NEW
    cumulative_filled: float = 0.0
    last_event_at: str | None = None

    def __post_init__(self):
        domain(self.domain)
        if not self.order_id or finite(self.quantity, "quantity", 0) == 0:
            raise ValueError("order identity and positive quantity required")
        finite(self.cumulative_filled, "filled quantity", 0, self.quantity)
        ExecutionState(self.state)
        if self.last_event_at:
            instant(self.last_event_at)

    def transition(self, state: ExecutionState, *, cumulative_filled: float, at: str, reconciled=False):
        stamp = instant(at)
        state = ExecutionState(state)
        finite(cumulative_filled, "filled quantity", self.cumulative_filled, self.quantity)
        if self.last_event_at and stamp < instant(self.last_event_at):
            raise ValueError("out-of-order execution event")
        if state is self.state and cumulative_filled == self.cumulative_filled:
            return self
        terminal = {ExecutionState.FILLED, ExecutionState.REJECTED, ExecutionState.CANCELLED, ExecutionState.EXPIRED}
        if self.state in terminal:
            raise ValueError("terminal order cannot be reopened")
        if self.state is ExecutionState.NEW and state not in {ExecutionState.SUBMITTED, ExecutionState.REJECTED}:
            raise ValueError("order must be submitted before a fill")
        if state is ExecutionState.NEW or self.state is not ExecutionState.NEW and state is ExecutionState.SUBMITTED:
            raise ValueError("execution transition cannot move backwards")
        if self.state is ExecutionState.UNKNOWN and not reconciled:
            raise ValueError("timeout needs broker reconciliation; blind retry prohibited")
        if state is ExecutionState.FILLED and cumulative_filled != self.quantity:
            raise ValueError("filled state requires exact cumulative quantity")
        if state is ExecutionState.PARTIAL and not 0 < cumulative_filled < self.quantity:
            raise ValueError("partial fill must be strictly between zero and order size")
        if state in {ExecutionState.REJECTED, ExecutionState.SUBMITTED} and cumulative_filled:
            raise ValueError("unfilled state cannot contain fills")
        return replace(self, state=state, cumulative_filled=cumulative_filled, last_event_at=stamp.isoformat())
