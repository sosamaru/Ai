from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic


@dataclass(slots=True)
class OrderGuard:
    ttl_seconds: float = 180.0
    _last_orders: dict[str, float] = field(default_factory=dict)

    def allow(self, symbol: str, side: str, now: float | None = None) -> bool:
        current = monotonic() if now is None else now
        key = f"{symbol}:{side.upper()}"
        previous = self._last_orders.get(key)
        if previous is not None and current - previous < self.ttl_seconds:
            return False
        self._last_orders[key] = current
        self._purge(current)
        return True

    def _purge(self, now: float) -> None:
        expired = [
            key for key, timestamp in self._last_orders.items()
            if now - timestamp >= self.ttl_seconds
        ]
        for key in expired:
            self._last_orders.pop(key, None)
