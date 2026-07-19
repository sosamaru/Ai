from __future__ import annotations

import hashlib
import json
import sqlite3
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock
from typing import Callable, Generic, TypeVar

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    maximum_delay_seconds: float = 2.0

    def __post_init__(self) -> None:
        if not 1 <= self.max_attempts <= 10:
            raise ValueError("max_attempts must be between 1 and 10")
        if self.base_delay_seconds < 0 or self.maximum_delay_seconds < self.base_delay_seconds:
            raise ValueError("invalid retry delays")


@dataclass(frozen=True, slots=True)
class CircuitBreakerPolicy:
    failure_threshold: int = 3
    recovery_timeout_seconds: float = 60.0

    def __post_init__(self) -> None:
        if self.failure_threshold < 1:
            raise ValueError("failure_threshold must be positive")
        if self.recovery_timeout_seconds <= 0:
            raise ValueError("recovery_timeout_seconds must be positive")


@dataclass(frozen=True, slots=True)
class ExecutionEvidence:
    provider: str
    operation: str
    status: str
    started_at_utc: str
    completed_at_utc: str
    attempts: int
    cache_hit: bool
    circuit_state: str
    error_type: str | None
    fingerprint: str


class SlidingWindowRateLimiter:
    def __init__(self, maximum_calls: int, period_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        if maximum_calls < 1 or period_seconds <= 0:
            raise ValueError("invalid rate limit")
        self.maximum_calls = maximum_calls
        self.period_seconds = period_seconds
        self._clock = clock
        self._calls: deque[float] = deque()
        self._lock = Lock()

    def acquire(self) -> None:
        with self._lock:
            now = self._clock()
            while self._calls and now - self._calls[0] >= self.period_seconds:
                self._calls.popleft()
            if len(self._calls) >= self.maximum_calls:
                raise RuntimeError("provider rate limit exceeded")
            self._calls.append(now)


class CircuitBreaker:
    def __init__(self, policy: CircuitBreakerPolicy, clock: Callable[[], float] = time.monotonic) -> None:
        self.policy = policy
        self._clock = clock
        self.failure_count = 0
        self.opened_at: float | None = None

    @property
    def state(self) -> str:
        if self.opened_at is None:
            return "CLOSED"
        if self._clock() - self.opened_at >= self.policy.recovery_timeout_seconds:
            return "HALF_OPEN"
        return "OPEN"

    def allow(self) -> bool:
        return self.state != "OPEN"

    def record_success(self) -> None:
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        self.failure_count += 1
        if self.failure_count >= self.policy.failure_threshold:
            self.opened_at = self._clock()


@dataclass(slots=True)
class _CacheEntry(Generic[T]):
    value: T
    expires_at: float


class TTLCache(Generic[T]):
    def __init__(self, ttl_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.ttl_seconds = ttl_seconds
        self._clock = clock
        self._entries: dict[str, _CacheEntry[T]] = {}

    def get(self, key: str) -> T | None:
        entry = self._entries.get(key)
        if entry is None:
            return None
        if self._clock() >= entry.expires_at:
            self._entries.pop(key, None)
            return None
        return entry.value

    def set(self, key: str, value: T) -> None:
        self._entries[key] = _CacheEntry(value=value, expires_at=self._clock() + self.ttl_seconds)


class ExecutionEvidenceStore:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS intelligence_execution_evidence (
                    evidence_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at_utc TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    fingerprint TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS intelligence_execution_evidence_no_update
                BEFORE UPDATE ON intelligence_execution_evidence
                BEGIN SELECT RAISE(ABORT, 'intelligence evidence is immutable'); END
                """
            )
            connection.execute(
                """
                CREATE TRIGGER IF NOT EXISTS intelligence_execution_evidence_no_delete
                BEFORE DELETE ON intelligence_execution_evidence
                BEGIN SELECT RAISE(ABORT, 'intelligence evidence is immutable'); END
                """
            )

    def append(self, evidence: ExecutionEvidence) -> None:
        payload = json.dumps(asdict(evidence), sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO intelligence_execution_evidence (
                    created_at_utc, provider, operation, status, fingerprint, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    evidence.provider,
                    evidence.operation,
                    evidence.status,
                    evidence.fingerprint,
                    payload,
                ),
            )


class ResilientExecutor(Generic[T]):
    def __init__(
        self,
        provider: str,
        *,
        retry_policy: RetryPolicy | None = None,
        breaker_policy: CircuitBreakerPolicy | None = None,
        rate_limiter: SlidingWindowRateLimiter | None = None,
        cache: TTLCache[T] | None = None,
        evidence_store: ExecutionEvidenceStore | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not provider.strip():
            raise ValueError("provider is required")
        self.provider = provider.strip().lower()
        self.retry_policy = retry_policy or RetryPolicy()
        self.breaker = CircuitBreaker(breaker_policy or CircuitBreakerPolicy())
        self.rate_limiter = rate_limiter
        self.cache = cache
        self.evidence_store = evidence_store
        self._sleeper = sleeper

    def execute(self, operation: str, cache_key: str, function: Callable[[], T]) -> T:
        if not operation.strip() or not cache_key.strip():
            raise ValueError("operation and cache_key are required")
        started = datetime.now(UTC)
        cached = self.cache.get(cache_key) if self.cache else None
        if cached is not None:
            self._record(operation, "CACHE_HIT", started, 0, True, None)
            return cached
        if not self.breaker.allow():
            self._record(operation, "BLOCKED", started, 0, False, "CircuitOpenError")
            raise RuntimeError("provider circuit is open")

        last_error: Exception | None = None
        for attempt in range(1, self.retry_policy.max_attempts + 1):
            try:
                if self.rate_limiter:
                    self.rate_limiter.acquire()
                value = function()
                self.breaker.record_success()
                if self.cache:
                    self.cache.set(cache_key, value)
                self._record(operation, "SUCCESS", started, attempt, False, None)
                return value
            except Exception as exc:
                last_error = exc
                self.breaker.record_failure()
                if attempt < self.retry_policy.max_attempts and self.breaker.allow():
                    delay = min(
                        self.retry_policy.maximum_delay_seconds,
                        self.retry_policy.base_delay_seconds * (2 ** (attempt - 1)),
                    )
                    self._sleeper(delay)
        assert last_error is not None
        self._record(operation, "FAILURE", started, self.retry_policy.max_attempts, False, type(last_error).__name__)
        raise last_error

    def _record(
        self,
        operation: str,
        status: str,
        started: datetime,
        attempts: int,
        cache_hit: bool,
        error_type: str | None,
    ) -> None:
        completed = datetime.now(UTC)
        canonical = {
            "provider": self.provider,
            "operation": operation,
            "status": status,
            "started_at_utc": started.isoformat(),
            "completed_at_utc": completed.isoformat(),
            "attempts": attempts,
            "cache_hit": cache_hit,
            "circuit_state": self.breaker.state,
            "error_type": error_type,
        }
        fingerprint = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        evidence = ExecutionEvidence(fingerprint=fingerprint, **canonical)
        if self.evidence_store:
            self.evidence_store.append(evidence)


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerPolicy",
    "ExecutionEvidence",
    "ExecutionEvidenceStore",
    "ResilientExecutor",
    "RetryPolicy",
    "SlidingWindowRateLimiter",
    "TTLCache",
]
