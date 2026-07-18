from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Protocol

from aipro.models import MarketSnapshot


class SnapshotProvider(Protocol):
    def snapshots(self) -> list[MarketSnapshot]: ...


class MarketDataHealthError(RuntimeError):
    """Raised when market data is unhealthy and strategy execution must stop."""


@dataclass(frozen=True, slots=True)
class MarketDataHealthPolicy:
    max_latency_sec: float = 10.0
    max_snapshot_age_sec: float = 120.0
    max_consecutive_failures: int = 3

    def __post_init__(self) -> None:
        if self.max_latency_sec <= 0:
            raise ValueError("max_latency_sec must be positive")
        if self.max_snapshot_age_sec <= 0:
            raise ValueError("max_snapshot_age_sec must be positive")
        if self.max_consecutive_failures < 1:
            raise ValueError("max_consecutive_failures must be at least 1")


@dataclass(slots=True)
class HealthCheckedMarketData:
    provider_name: str
    delegate: SnapshotProvider
    policy: MarketDataHealthPolicy = MarketDataHealthPolicy()
    monotonic: Callable[[], float] = time.monotonic
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc)
    consecutive_failures: int = 0
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_latency_sec: float | None = None
    last_source_timestamp_at: datetime | None = None
    last_error: str | None = None

    def snapshots(self) -> list[MarketSnapshot]:
        started = self.monotonic()
        try:
            snapshots = self.delegate.snapshots()
            latency = self.monotonic() - started
            if latency < 0 or latency > self.policy.max_latency_sec:
                raise MarketDataHealthError(
                    f"market data latency exceeded limit: {latency:.3f}s"
                )
            if not snapshots:
                raise MarketDataHealthError("market data returned no snapshots")
            source_timestamp = self._validate_source_timestamps(snapshots)
        except Exception as exc:
            self.consecutive_failures += 1
            self.last_failure_at = self.now()
            self.last_error = f"{type(exc).__name__}: {exc}"
            raise MarketDataHealthError(self.last_error) from exc

        self.consecutive_failures = 0
        self.last_success_at = self.now()
        self.last_latency_sec = latency
        self.last_source_timestamp_at = source_timestamp
        self.last_error = None
        return snapshots

    def _validate_source_timestamps(
        self, snapshots: list[MarketSnapshot]
    ) -> datetime | None:
        timestamps: list[datetime] = []
        require_exchange_timestamps = self.provider_name.upper() == "UPBIT"
        current = self.now()
        for snapshot in snapshots:
            pair = (snapshot.ticker_timestamp, snapshot.candle_timestamp)
            if require_exchange_timestamps and any(value is None for value in pair):
                raise MarketDataHealthError(
                    f"missing exchange timestamp for {snapshot.symbol}"
                )
            for value in pair:
                if value is None:
                    continue
                if value.tzinfo is None:
                    raise MarketDataHealthError(
                        f"naive exchange timestamp for {snapshot.symbol}"
                    )
                normalized = value.astimezone(timezone.utc)
                age = (current - normalized).total_seconds()
                if age < -1.0:
                    raise MarketDataHealthError(
                        f"future exchange timestamp for {snapshot.symbol}: age={age:.1f}s"
                    )
                if age > self.policy.max_snapshot_age_sec:
                    raise MarketDataHealthError(
                        f"stale exchange timestamp for {snapshot.symbol}: age={age:.1f}s"
                    )
                timestamps.append(normalized)
        if not timestamps:
            return None
        spread = (max(timestamps) - min(timestamps)).total_seconds()
        if spread > self.policy.max_snapshot_age_sec:
            raise MarketDataHealthError(
                f"inconsistent exchange timestamps: spread={spread:.1f}s"
            )
        return max(timestamps)

    def assert_fresh(self) -> None:
        if self.last_success_at is None:
            return
        age = (self.now() - self.last_success_at).total_seconds()
        if age < 0 or age > self.policy.max_snapshot_age_sec:
            raise MarketDataHealthError(f"market data snapshot is stale: age={age:.1f}s")
        if self.last_source_timestamp_at is not None:
            source_age = (self.now() - self.last_source_timestamp_at).total_seconds()
            if source_age < -1.0 or source_age > self.policy.max_snapshot_age_sec:
                raise MarketDataHealthError(
                    f"exchange source timestamp is stale: age={source_age:.1f}s"
                )
        if self.consecutive_failures >= self.policy.max_consecutive_failures:
            raise MarketDataHealthError(
                f"market data consecutive failures reached {self.consecutive_failures}"
            )

    def health_status(self) -> dict[str, object]:
        age_sec: float | None = None
        source_age_sec: float | None = None
        if self.last_success_at is not None:
            age_sec = max(0.0, (self.now() - self.last_success_at).total_seconds())
        if self.last_source_timestamp_at is not None:
            source_age_sec = max(
                0.0, (self.now() - self.last_source_timestamp_at).total_seconds()
            )
        healthy = (
            self.last_error is None
            and self.consecutive_failures < self.policy.max_consecutive_failures
            and (age_sec is None or age_sec <= self.policy.max_snapshot_age_sec)
            and (
                source_age_sec is None
                or source_age_sec <= self.policy.max_snapshot_age_sec
            )
            and (
                self.last_latency_sec is None
                or self.last_latency_sec <= self.policy.max_latency_sec
            )
        )
        return {
            "provider": self.provider_name,
            "healthy": healthy,
            "consecutive_failures": self.consecutive_failures,
            "last_latency_sec": self.last_latency_sec,
            "last_success_at": None
            if self.last_success_at is None
            else self.last_success_at.isoformat(),
            "last_failure_at": None
            if self.last_failure_at is None
            else self.last_failure_at.isoformat(),
            "last_source_timestamp_at": None
            if self.last_source_timestamp_at is None
            else self.last_source_timestamp_at.isoformat(),
            "snapshot_age_sec": age_sec,
            "source_age_sec": source_age_sec,
            "last_error": self.last_error,
        }


__all__ = [
    "HealthCheckedMarketData",
    "MarketDataHealthError",
    "MarketDataHealthPolicy",
    "SnapshotProvider",
]
