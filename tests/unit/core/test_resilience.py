from app.core.resilience import (
    CircuitBreaker,
    CircuitBreakerPolicy,
    RetryPolicy,
    TimeoutPolicy,
)


def test_retry_policy_retries_transient_status_before_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, retry_status_codes=(429, 500))

    decision = policy.decision(attempt=1, status_code=429)

    assert decision.should_retry is True
    assert decision.next_delay_seconds == 0.0


def test_retry_policy_stops_at_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, retry_status_codes=(429,))

    decision = policy.decision(attempt=3, status_code=429)

    assert decision.should_retry is False
    assert decision.next_delay_seconds is None


def test_retry_policy_ignores_non_retryable_statuses() -> None:
    policy = RetryPolicy(max_attempts=3, retry_status_codes=(429,))

    decision = policy.decision(attempt=1, status_code=400)

    assert decision.should_retry is False


def test_retry_policy_retries_exceptions_when_enabled() -> None:
    policy = RetryPolicy(max_attempts=2, retry_exceptions=True)

    decision = policy.decision(attempt=1, error=RuntimeError("timeout"))

    assert decision.should_retry is True


def test_circuit_breaker_opens_after_threshold_failures() -> None:
    breaker = CircuitBreaker(failure_threshold=2, failure_status_range=range(400, 500))

    breaker.record_failure(status_code=429)
    assert breaker.allows_request() is True

    breaker.record_failure(status_code=400)

    assert breaker.allows_request() is False
    assert breaker.is_open is True


def test_circuit_breaker_ignores_statuses_outside_failure_range() -> None:
    breaker = CircuitBreaker(failure_threshold=1, failure_status_range=range(400, 500))

    breaker.record_failure(status_code=500)

    assert breaker.allows_request() is True


def test_circuit_breaker_success_resets_failures_and_closes() -> None:
    breaker = CircuitBreaker(failure_threshold=1, failure_status_range=range(400, 500))
    breaker.record_failure(status_code=429)

    breaker.record_success()

    assert breaker.failure_count == 0
    assert breaker.allows_request() is True


def test_circuit_breaker_policy_builds_stateful_breaker() -> None:
    policy = CircuitBreakerPolicy(
        failure_threshold=2,
        failure_status_range=range(400, 500),
    )

    breaker = policy.build()

    breaker.record_failure(status_code=429)
    breaker.record_failure(status_code=400)
    assert breaker.is_open is True


def test_timeout_policy_rejects_non_positive_timeout() -> None:
    try:
        TimeoutPolicy(timeout_seconds=0)
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("TimeoutPolicy accepted a non-positive timeout")
