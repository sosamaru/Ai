from __future__ import annotations

import sqlite3

import pytest

from aipro.intelligence.resilience import (
    CircuitBreakerPolicy,
    ExecutionEvidenceStore,
    ResilientExecutor,
    RetryPolicy,
    SlidingWindowRateLimiter,
    TTLCache,
)


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def test_retry_then_cache_hit() -> None:
    calls = 0
    cache: TTLCache[str] = TTLCache(60)
    executor = ResilientExecutor[str](
        "demo",
        retry_policy=RetryPolicy(max_attempts=3, base_delay_seconds=0, maximum_delay_seconds=0),
        cache=cache,
        sleeper=lambda _: None,
    )

    def operation() -> str:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise TimeoutError("temporary")
        return "ok"

    assert executor.execute("news", "BTC", operation) == "ok"
    assert executor.execute("news", "BTC", operation) == "ok"
    assert calls == 2


def test_circuit_opens_after_threshold() -> None:
    executor = ResilientExecutor[str](
        "demo",
        retry_policy=RetryPolicy(max_attempts=1, base_delay_seconds=0, maximum_delay_seconds=0),
        breaker_policy=CircuitBreakerPolicy(failure_threshold=2, recovery_timeout_seconds=60),
    )

    for _ in range(2):
        with pytest.raises(ValueError):
            executor.execute("news", "BTC", lambda: (_ for _ in ()).throw(ValueError("bad")))

    with pytest.raises(RuntimeError, match="circuit is open"):
        executor.execute("news", "BTC", lambda: "unreachable")


def test_rate_limiter_fails_closed() -> None:
    clock = Clock()
    limiter = SlidingWindowRateLimiter(2, 60, clock=clock)
    limiter.acquire()
    limiter.acquire()
    with pytest.raises(RuntimeError, match="rate limit"):
        limiter.acquire()
    clock.value = 61
    limiter.acquire()


def test_ttl_cache_expires() -> None:
    clock = Clock()
    cache: TTLCache[int] = TTLCache(10, clock=clock)
    cache.set("x", 1)
    assert cache.get("x") == 1
    clock.value = 10
    assert cache.get("x") is None


def test_evidence_store_is_append_only(tmp_path) -> None:
    database = tmp_path / "intelligence.sqlite3"
    store = ExecutionEvidenceStore(database)
    executor = ResilientExecutor[str]("demo", evidence_store=store)
    assert executor.execute("news", "BTC", lambda: "ok") == "ok"

    with sqlite3.connect(database) as connection:
        count = connection.execute("SELECT COUNT(*) FROM intelligence_execution_evidence").fetchone()[0]
        assert count == 1
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE intelligence_execution_evidence SET status = 'FAILURE'")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("DELETE FROM intelligence_execution_evidence")
