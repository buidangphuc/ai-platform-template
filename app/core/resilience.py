from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    next_delay_seconds: float | None = None


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    retry_status_codes: tuple[int, ...] = (408, 429, 500, 502, 503, 504)
    retry_exceptions: bool = True
    backoff_seconds: tuple[float, ...] = (0.0, 0.25, 1.0)

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if not self.backoff_seconds:
            raise ValueError("backoff_seconds must not be empty")
        if any(delay < 0 for delay in self.backoff_seconds):
            raise ValueError("backoff_seconds must not contain negative values")

    def decision(
        self,
        *,
        attempt: int,
        status_code: int | None = None,
        error: BaseException | None = None,
    ) -> RetryDecision:
        if attempt >= self.max_attempts:
            return RetryDecision(should_retry=False)
        if error is not None and self.retry_exceptions:
            return RetryDecision(True, self._delay_for_attempt(attempt))
        if status_code in self.retry_status_codes:
            return RetryDecision(True, self._delay_for_attempt(attempt))
        return RetryDecision(should_retry=False)

    def _delay_for_attempt(self, attempt: int) -> float:
        index = max(min(attempt - 1, len(self.backoff_seconds) - 1), 0)
        return self.backoff_seconds[index]


@dataclass(frozen=True)
class TimeoutPolicy:
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    failure_threshold: int = 3
    failure_status_codes: tuple[int, ...] = ()
    failure_status_range: range | None = None

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")

    def build(self) -> CircuitBreaker:
        return CircuitBreaker(
            failure_threshold=self.failure_threshold,
            failure_status_codes=self.failure_status_codes,
            failure_status_range=self.failure_status_range,
        )


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        failure_status_codes: tuple[int, ...] = (),
        failure_status_range: range | None = None,
    ) -> None:
        if failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        self.failure_threshold = failure_threshold
        self.failure_status_codes = failure_status_codes
        self.failure_status_range = failure_status_range
        self.failure_count = 0
        self.is_open = False

    def allows_request(self) -> bool:
        return not self.is_open

    def record_success(self) -> None:
        self.failure_count = 0
        self.is_open = False

    def record_failure(self, *, status_code: int | None = None) -> None:
        if not self._counts_as_failure(status_code):
            return
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.is_open = True

    def reset(self) -> None:
        self.record_success()

    def _counts_as_failure(self, status_code: int | None) -> bool:
        if status_code is None:
            return False
        if status_code in self.failure_status_codes:
            return True
        return (
            self.failure_status_range is not None
            and status_code in self.failure_status_range
        )
