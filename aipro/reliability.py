from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


class RetryableBrokerError(RuntimeError):
    """A transient broker failure that may be retried safely."""


class PermanentBrokerError(RuntimeError):
    """A broker failure that must not be retried."""


class BrokerTimeoutError(TimeoutError):
    """Raised when a broker operation exceeds its configured deadline."""


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    timeout_sec: float = 5.0
    initial_backoff_sec: float = 0.25
    backoff_multiplier: float = 2.0
    max_backoff_sec: float = 2.0

    def validate(self) -> None:
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        if self.timeout_sec <= 0:
            raise ValueError("timeout_sec must be positive")
        if self.initial_backoff_sec < 0:
            raise ValueError("initial_backoff_sec must be non-negative")
        if self.backoff_multiplier < 1:
            raise ValueError("backoff_multiplier must be at least 1")
        if self.max_backoff_sec < 0:
            raise ValueError("max_backoff_sec must be non-negative")


class BrokerOperationExecutor:
    def __init__(
        self,
        policy: RetryPolicy | None = None,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self.policy = policy or RetryPolicy()
        self.policy.validate()
        self._clock = clock
        self._sleeper = sleeper

    def execute(self, operation: Callable[[], T]) -> T:
        started = self._clock()
        backoff = self.policy.initial_backoff_sec
        last_error: RetryableBrokerError | None = None

        for attempt in range(1, self.policy.max_attempts + 1):
            if self._clock() - started >= self.policy.timeout_sec:
                raise BrokerTimeoutError("broker operation deadline exceeded") from last_error

            try:
                result = operation()
            except PermanentBrokerError:
                raise
            except RetryableBrokerError as exc:
                last_error = exc
                if attempt >= self.policy.max_attempts:
                    raise
                remaining = self.policy.timeout_sec - (self._clock() - started)
                if remaining <= 0:
                    raise BrokerTimeoutError("broker operation deadline exceeded") from exc
                delay = min(backoff, self.policy.max_backoff_sec, remaining)
                if delay > 0:
                    self._sleeper(delay)
                backoff = min(
                    backoff * self.policy.backoff_multiplier,
                    self.policy.max_backoff_sec,
                )
                continue

            if self._clock() - started > self.policy.timeout_sec:
                raise BrokerTimeoutError(
                    "broker operation completed after its deadline; reconcile before retrying"
                )
            return result

        raise RuntimeError("unreachable broker retry state")
