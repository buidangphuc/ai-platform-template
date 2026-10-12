from typing import ClassVar

import pytest

from app.core.resilience import (
    BreakerState,
    CircuitBreaker,
    CircuitBreakerPolicy,
    RetryPolicy,
    TimeoutPolicy,
    error_status_code,
    is_transient_error,
    retry_after_seconds,
)


class _StatusError(Exception):
    def __init__(self, status_code: int, *, retry_after: float | None = None) -> None:
        super().__init__(f"status {status_code}")
        self.status_code = status_code
        if retry_after is not None:
            self.retry_after = retry_after


class APITimeoutError(Exception):
    """Stand-in for provider SDK timeouts (matched by class name)."""


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# ------------------------------------------------------------ classification


@pytest.mark.parametrize("status", [408, 429, 500, 502, 503, 504, 529])
def test_transient_statuses(status: int) -> None:
    assert is_transient_error(_StatusError(status)) is True


@pytest.mark.parametrize("status", [400, 401, 403, 404, 413, 422])
def test_deterministic_4xx_is_not_transient(status: int) -> None:
    assert is_transient_error(_StatusError(status)) is False


def test_timeouts_and_connection_errors_are_transient() -> None:
    assert is_transient_error(TimeoutError()) is True
    assert is_transient_error(ConnectionResetError()) is True
    assert is_transient_error(APITimeoutError()) is True


def test_unknown_exceptions_are_not_transient() -> None:
    assert is_transient_error(ValueError("bad prompt")) is False
    assert is_transient_error(RuntimeError("boom")) is False


def test_status_code_is_read_from_response_attribute() -> None:
    class _Response:
        status_code = 503
        headers: ClassVar[dict[str, str]] = {"retry-after": "7"}

    error = Exception("x")
    error.response = _Response()  # type: ignore[attr-defined]

    assert error_status_code(error) == 503
    assert retry_after_seconds(error) == 7.0
    assert is_transient_error(error) is True


def test_retry_after_prefers_attribute_and_ignores_garbage() -> None:
    assert retry_after_seconds(_StatusError(429, retry_after=3.0)) == 3.0
    assert retry_after_seconds(_StatusError(429)) is None
    error = Exception("x")
    error.retry_after = "soon"  # type: ignore[attr-defined]
    assert retry_after_seconds(error) is None


# ----------------------------------------------------------------- RetryPolicy


def test_retry_policy_retries_transient_status_before_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, retry_status_codes=(429, 500))

    decision = policy.decision(attempt=1, status_code=429)

    assert decision.should_retry is True


def test_retry_policy_stops_at_max_attempts() -> None:
    policy = RetryPolicy(max_attempts=3, retry_status_codes=(429,))

    decision = policy.decision(attempt=3, status_code=429)

    assert decision.should_retry is False
    assert decision.next_delay_seconds is None


def test_retry_policy_ignores_non_retryable_statuses() -> None:
    policy = RetryPolicy(max_attempts=3, retry_status_codes=(429,))

    assert policy.decision(attempt=1, status_code=400).should_retry is False


def test_retry_policy_default_retries_only_transient_errors() -> None:
    policy = RetryPolicy(max_attempts=3)

    assert policy.decision(attempt=1, error=TimeoutError()).should_retry is True
    assert policy.decision(attempt=1, error=_StatusError(503)).should_retry is True
    assert policy.decision(attempt=1, error=_StatusError(400)).should_retry is False
    assert policy.decision(attempt=1, error=ValueError("bad")).should_retry is False


def test_retry_policy_retry_on_override_retries_everything() -> None:
    policy = RetryPolicy(max_attempts=2, retry_on=lambda _error: True)

    assert policy.decision(attempt=1, error=RuntimeError("x")).should_retry is True


def test_retry_policy_does_not_retry_errors_when_disabled() -> None:
    policy = RetryPolicy(max_attempts=3, retry_exceptions=False)

    assert policy.decision(attempt=1, error=TimeoutError()).should_retry is False


def test_retry_policy_backoff_is_capped_exponential_with_full_jitter() -> None:
    top = RetryPolicy(
        max_attempts=10,
        base_delay_seconds=1.0,
        max_delay_seconds=5.0,
        rng=lambda: 1.0,
    )
    assert [
        top.decision(attempt=n, status_code=503).next_delay_seconds
        for n in (1, 2, 3, 4, 5)
    ] == [1.0, 2.0, 4.0, 5.0, 5.0]

    bottom = RetryPolicy(
        max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=5.0, rng=lambda: 0.0
    )
    assert bottom.decision(attempt=3, status_code=503).next_delay_seconds == 0.0

    half = RetryPolicy(
        max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=5.0, rng=lambda: 0.5
    )
    assert half.decision(attempt=3, status_code=503).next_delay_seconds == 2.0


def test_retry_policy_honors_retry_after_hint_up_to_the_cap() -> None:
    policy = RetryPolicy(
        max_attempts=3, base_delay_seconds=1.0, max_delay_seconds=30.0, rng=lambda: 0.0
    )

    hinted = policy.decision(attempt=1, error=_StatusError(429, retry_after=12.0))
    explicit = policy.decision(attempt=1, status_code=429, retry_after_seconds=4.0)
    huge = policy.decision(attempt=1, error=_StatusError(429, retry_after=3600.0))

    assert hinted.next_delay_seconds == 12.0
    assert explicit.next_delay_seconds == 4.0
    assert huge.next_delay_seconds == 30.0


def test_retry_policy_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        RetryPolicy(max_attempts=0)
    with pytest.raises(ValueError):
        RetryPolicy(base_delay_seconds=-1.0)
    with pytest.raises(ValueError):
        RetryPolicy(base_delay_seconds=2.0, max_delay_seconds=1.0)


# -------------------------------------------------------------- CircuitBreaker


def _breaker(clock: _Clock, *, threshold: int = 2, cooldown: float = 30.0):
    return CircuitBreaker(
        failure_threshold=threshold, cooldown_seconds=cooldown, clock=clock
    )


def test_breaker_opens_after_threshold_of_transient_failures() -> None:
    breaker = _breaker(_Clock())

    breaker.record_failure(_StatusError(429))
    assert breaker.state is BreakerState.CLOSED
    breaker.record_failure(_StatusError(503))

    assert breaker.state is BreakerState.OPEN
    assert breaker.try_acquire() is False


def test_breaker_counts_timeouts_and_connection_errors() -> None:
    breaker = _breaker(_Clock())

    breaker.record_failure(TimeoutError())
    breaker.record_failure(ConnectionError())

    assert breaker.state is BreakerState.OPEN


def test_breaker_ignores_deterministic_errors() -> None:
    breaker = _breaker(_Clock(), threshold=1)

    breaker.record_failure(_StatusError(400))
    breaker.record_failure(_StatusError(401))
    breaker.record_failure(ValueError("content policy"))

    assert breaker.state is BreakerState.CLOSED
    assert breaker.try_acquire() is True


def test_breaker_success_resets_consecutive_failures() -> None:
    breaker = _breaker(_Clock())

    breaker.record_failure(TimeoutError())
    breaker.record_success()
    breaker.record_failure(TimeoutError())

    assert breaker.state is BreakerState.CLOSED


def test_breaker_stays_open_until_cooldown_then_grants_single_probe() -> None:
    clock = _Clock()
    breaker = _breaker(clock, threshold=1, cooldown=30.0)
    breaker.record_failure(TimeoutError())

    clock.now += 29.9
    assert breaker.try_acquire() is False

    clock.now += 0.2
    assert breaker.try_acquire() is True  # the probe
    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.try_acquire() is False  # everyone else keeps failing over


def test_breaker_probe_success_closes() -> None:
    clock = _Clock()
    breaker = _breaker(clock, threshold=1)
    breaker.record_failure(TimeoutError())
    clock.now += 31
    assert breaker.try_acquire() is True

    breaker.record_success()

    assert breaker.state is BreakerState.CLOSED
    assert breaker.try_acquire() is True
    assert breaker.try_acquire() is True


def test_breaker_probe_failure_reopens_with_fresh_cooldown() -> None:
    clock = _Clock()
    breaker = _breaker(clock, threshold=3, cooldown=30.0)
    for _ in range(3):
        breaker.record_failure(TimeoutError())
    clock.now += 31
    assert breaker.try_acquire() is True

    breaker.record_failure(_StatusError(503))  # one failure is enough in half-open

    assert breaker.state is BreakerState.OPEN
    clock.now += 29
    assert breaker.try_acquire() is False
    clock.now += 2
    assert breaker.try_acquire() is True


def test_breaker_deterministic_error_on_probe_releases_probe_without_closing() -> None:
    clock = _Clock()
    breaker = _breaker(clock, threshold=1)
    breaker.record_failure(TimeoutError())
    clock.now += 31
    assert breaker.try_acquire() is True

    breaker.record_failure(_StatusError(400))

    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.try_acquire() is True  # probe slot is free again


def test_breaker_abandoned_probe_lease_expires() -> None:
    clock = _Clock()
    breaker = _breaker(clock, threshold=1, cooldown=30.0)
    breaker.record_failure(TimeoutError())
    clock.now += 31
    assert breaker.try_acquire() is True  # caller never reports back

    clock.now += 29
    assert breaker.try_acquire() is False
    clock.now += 2
    assert breaker.try_acquire() is True


def test_breaker_policy_builds_stateful_breaker() -> None:
    clock = _Clock()
    policy = CircuitBreakerPolicy(failure_threshold=2, cooldown_seconds=5.0)

    breaker = policy.build(clock=clock)

    breaker.record_failure(TimeoutError())
    breaker.record_failure(TimeoutError())
    assert breaker.state is BreakerState.OPEN
    clock.now += 6
    assert breaker.try_acquire() is True


def test_breaker_policy_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError):
        CircuitBreakerPolicy(failure_threshold=0)
    with pytest.raises(ValueError):
        CircuitBreakerPolicy(cooldown_seconds=0)


def test_timeout_policy_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="positive"):
        TimeoutPolicy(timeout_seconds=0)


def test_released_probe_can_be_retaken_without_another_cooldown() -> None:
    clock = _Clock()
    breaker = _breaker(clock, threshold=1, cooldown=30.0)
    breaker.record_failure(_StatusError(503))
    clock.now += 31

    assert breaker.try_acquire() is True  # half-open probe taken
    assert breaker.try_acquire() is False  # slot held
    breaker.release_probe()  # our own deadline cut the probe short

    assert breaker.state is BreakerState.HALF_OPEN
    assert breaker.try_acquire() is True
