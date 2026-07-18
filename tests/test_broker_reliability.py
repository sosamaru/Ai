import pytest

from aipro.reliability import (
    BrokerOperationExecutor,
    BrokerTimeoutError,
    PermanentBrokerError,
    RetryableBrokerError,
    RetryPolicy,
)


def test_retryable_failure_eventually_succeeds_with_bounded_attempts() -> None:
    attempts = 0
    sleeps: list[float] = []

    def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise RetryableBrokerError("temporary outage")
        return "filled"

    executor = BrokerOperationExecutor(
        RetryPolicy(max_attempts=3, timeout_sec=10, initial_backoff_sec=0.5),
        sleeper=sleeps.append,
    )

    assert executor.execute(operation) == "filled"
    assert attempts == 3
    assert sleeps == [0.5, 1.0]


def test_permanent_failure_is_not_retried() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise PermanentBrokerError("invalid order")

    executor = BrokerOperationExecutor(sleeper=lambda _: None)
    with pytest.raises(PermanentBrokerError, match="invalid order"):
        executor.execute(operation)
    assert attempts == 1


def test_retry_limit_preserves_original_failure() -> None:
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise RetryableBrokerError("still unavailable")

    executor = BrokerOperationExecutor(
        RetryPolicy(max_attempts=2, timeout_sec=10, initial_backoff_sec=0),
        sleeper=lambda _: None,
    )
    with pytest.raises(RetryableBrokerError, match="still unavailable"):
        executor.execute(operation)
    assert attempts == 2


def test_deadline_blocks_another_attempt() -> None:
    times = iter([0.0, 0.0, 0.6, 1.1])
    attempts = 0

    def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise RetryableBrokerError("temporary")

    executor = BrokerOperationExecutor(
        RetryPolicy(max_attempts=3, timeout_sec=1.0, initial_backoff_sec=0),
        clock=lambda: next(times),
        sleeper=lambda _: None,
    )
    with pytest.raises(BrokerTimeoutError):
        executor.execute(operation)
    assert attempts == 1


def test_invalid_policy_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_attempts"):
        BrokerOperationExecutor(RetryPolicy(max_attempts=0))
