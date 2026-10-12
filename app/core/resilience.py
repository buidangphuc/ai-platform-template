"""Retry, timeout and circuit-breaker primitives.

"Transient" is defined once here (``is_transient_error``) and shared by the
retry policy and the breaker, so a deterministic failure (bad prompt, context
length, content policy: a 4xx other than 408/429) is never retried and never
trips failover, while overload and unreachable-provider failures do.
"""

from __future__ import annotations

import random
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from time import monotonic

TRANSIENT_STATUS_CODES = frozenset({408, 429})

# Provider/HTTP client exceptions that do not derive from the builtin
# TimeoutError/ConnectionError (openai, anthropic and httpx SDKs). Matched by
# class name so this module stays free of optional-dependency imports.
_TRANSIENT_ERROR_NAMES = frozenset(
    {
        "APITimeoutError",
        "APIConnectionError",
        "TimeoutException",
        "TransportError",
    }
)


def error_status_code(error: BaseException) -> int | None:
    """HTTP status carried by ``error`` (directly or via ``.response``), if any."""
    status = getattr(error, "status_code", None)
    if isinstance(status, int):
        return status
    status = getattr(getattr(error, "response", None), "status_code", None)
    return status if isinstance(status, int) else None


def retry_after_seconds(error: BaseException) -> float | None:
    """Server retry hint in seconds: ``.retry_after`` or a ``Retry-After`` header."""
    hint = getattr(error, "retry_after", None)
    if hint is None:
        headers = getattr(getattr(error, "response", None), "headers", None)
        hint = headers.get("retry-after") if headers is not None else None
    try:
        seconds = float(hint) if hint is not None else None
    except (TypeError, ValueError):
        return None
    return seconds if seconds is not None and seconds >= 0 else None


def is_transient_error(error: BaseException) -> bool:
    """True for failures that a later attempt or another provider can fix.

    Transient: 408, 429, any 5xx, timeouts and connection errors. Everything
    else (other 4xx, parsing/validation errors, unknown exceptions) is
    deterministic: retrying or failing over would only repeat the failure.
    """
    status = error_status_code(error)
    if status is not None:
        return status in TRANSIENT_STATUS_CODES or status >= 500
    if isinstance(error, TimeoutError | ConnectionError):
        return True
    return any(cls.__name__ in _TRANSIENT_ERROR_NAMES for cls in type(error).__mro__)


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    next_delay_seconds: float | None = None


@dataclass(frozen=True)
class RetryPolicy:
    """Capped exponential backoff with full jitter.

    The delay before retry ``n`` is ``rng() * min(max_delay, base * 2**(n-1))``.
    A ``Retry-After`` hint (argument or carried by the error) raises the delay
    to the hint, itself capped at ``max_delay_seconds``. Errors are retried
    only when ``retry_on(error)`` is true (default: ``is_transient_error``).
    """

    max_attempts: int = 3
    retry_status_codes: tuple[int, ...] = (408, 429, 500, 502, 503, 504)
    retry_exceptions: bool = True
    retry_on: Callable[[BaseException], bool] = is_transient_error
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 30.0
    rng: Callable[[], float] = random.random

    def __post_init__(self) -> None:
        if self.max_attempts <= 0:
            raise ValueError("max_attempts must be positive")
        if self.base_delay_seconds < 0:
            raise ValueError("base_delay_seconds must not be negative")
        if self.max_delay_seconds < self.base_delay_seconds:
            raise ValueError("max_delay_seconds must be >= base_delay_seconds")

    def decision(
        self,
        *,
        attempt: int,
        status_code: int | None = None,
        error: BaseException | None = None,
        retry_after_seconds: float | None = None,
    ) -> RetryDecision:
        if attempt >= self.max_attempts:
            return RetryDecision(should_retry=False)
        if error is not None:
            if not (self.retry_exceptions and self.retry_on(error)):
                return RetryDecision(should_retry=False)
            if retry_after_seconds is None:
                retry_after_seconds = _error_retry_after(error)
        elif status_code not in self.retry_status_codes:
            return RetryDecision(should_retry=False)
        return RetryDecision(True, self._delay(attempt, retry_after_seconds))

    def _delay(self, attempt: int, retry_after: float | None) -> float:
        ceiling = min(
            self.max_delay_seconds, self.base_delay_seconds * 2 ** (attempt - 1)
        )
        delay = self.rng() * ceiling
        if retry_after is not None:
            delay = max(delay, min(retry_after, self.max_delay_seconds))
        return delay


def _error_retry_after(error: BaseException) -> float | None:
    return retry_after_seconds(error)


@dataclass(frozen=True)
class TimeoutPolicy:
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass(frozen=True)
class CircuitBreakerPolicy:
    failure_threshold: int = 3
    cooldown_seconds: float = 30.0

    def __post_init__(self) -> None:
        if self.failure_threshold <= 0:
            raise ValueError("failure_threshold must be positive")
        if self.cooldown_seconds <= 0:
            raise ValueError("cooldown_seconds must be positive")

    def build(self, *, clock: Callable[[], float] | None = None) -> CircuitBreaker:
        return CircuitBreaker(
            failure_threshold=self.failure_threshold,
            cooldown_seconds=self.cooldown_seconds,
            clock=clock,
        )


class CircuitBreaker:
    """closed -> open -> half-open -> closed, counting transient failures only.

    ``try_acquire`` is the single admission gate: closed admits everyone; open
    rejects until ``cooldown_seconds`` has passed, then admits exactly one
    probe (half-open) whose outcome decides: success closes, a transient
    failure reopens with a fresh cooldown. A probe that is never reported
    (cancelled caller) is re-granted after one more cooldown, so the breaker
    cannot wedge half-open.

    Single-event-loop use; not thread-safe.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock: Callable[[], float] | None = None,
    ) -> None:
        CircuitBreakerPolicy(failure_threshold, cooldown_seconds)  # validates
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.clock = clock or monotonic
        self.failure_count = 0
        self.state = BreakerState.CLOSED
        self._open_until = 0.0
        self._probe_lease_until: float | None = None

    def try_acquire(self) -> bool:
        now = self.clock()
        if self.state is BreakerState.CLOSED:
            return True
        if self.state is BreakerState.OPEN:
            if now < self._open_until:
                return False
            self.state = BreakerState.HALF_OPEN
            self._probe_lease_until = None
        if self._probe_lease_until is not None and now < self._probe_lease_until:
            return False
        self._probe_lease_until = now + self.cooldown_seconds
        return True

    def release_probe(self) -> None:
        """Give back a half-open probe slot whose attempt was abandoned by the
        caller (e.g. its own deadline); says nothing about provider health."""
        self._probe_lease_until = None

    def record_success(self) -> None:
        self.failure_count = 0
        self.state = BreakerState.CLOSED
        self._probe_lease_until = None

    def record_failure(self, error: BaseException) -> None:
        if not is_transient_error(error):
            # Deterministic failure: says nothing about provider health. Free
            # the probe slot so the next call can probe again.
            self._probe_lease_until = None
            return
        if self.state is BreakerState.HALF_OPEN:
            self._open()
            return
        if self.state is BreakerState.OPEN:
            return
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open()

    def reset(self) -> None:
        self.record_success()

    def _open(self) -> None:
        self.state = BreakerState.OPEN
        self._open_until = self.clock() + self.cooldown_seconds
        self._probe_lease_until = None
