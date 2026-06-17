from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

DEFAULT_EVICTION_THRESHOLD = 10_000


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int
    retry_after_seconds: int | None = None


class InMemoryRateLimiter:
    """Sliding-window-counter rate limiter (in-memory).

    Each ``(key, window_index)`` pair holds the count for that minute (or
    whatever ``window_seconds`` is). At check time the limiter blends the
    current window count with a weighted slice of the previous window,
    smoothing the boundary so callers cannot burst ``2 * limit`` requests
    by straddling two fixed windows.

    Blocked requests do not increment the counter (no Redis-style explosion).
    Expired window buckets are evicted lazily once the table grows past
    ``eviction_threshold``.
    """

    def __init__(
        self,
        limit: int,
        window_seconds: int = 60,
        *,
        clock: Callable[[], float] | None = None,
        eviction_threshold: int = DEFAULT_EVICTION_THRESHOLD,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if eviction_threshold <= 0:
            raise ValueError("eviction_threshold must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock or monotonic
        self.eviction_threshold = eviction_threshold
        self._counts: dict[tuple[str, int], int] = {}

    async def check(self, key: str) -> RateLimitResult:
        now = self.clock()
        window_index = int(now // self.window_seconds)
        elapsed = now - window_index * self.window_seconds
        previous_weight = max(1.0 - elapsed / self.window_seconds, 0.0)

        self._evict_if_needed(window_index)

        current = self._counts.get((key, window_index), 0)
        previous = self._counts.get((key, window_index - 1), 0)
        weighted = current + int(previous * previous_weight)

        if weighted >= self.limit:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=max(int(self.window_seconds - elapsed), 1),
            )

        self._counts[(key, window_index)] = current + 1
        weighted_after = (current + 1) + int(previous * previous_weight)
        return RateLimitResult(
            allowed=True,
            remaining=max(self.limit - weighted_after, 0),
        )

    def _evict_if_needed(self, current_window_index: int) -> None:
        if len(self._counts) < self.eviction_threshold:
            return
        stale_threshold = current_window_index - 1
        expired = [bucket for bucket in self._counts if bucket[1] < stale_threshold]
        for bucket in expired:
            del self._counts[bucket]


class RedisRateLimiter:
    """Sliding-window-counter rate limiter (Redis).

    Uses two keys per ``(prefix, key)``: one for the current window, one for
    the previous. The previous key's TTL is set to ``2 * window_seconds`` so
    it survives long enough to influence weighting. The Lua script is
    atomic — no race between the check and increment.
    """

    _CHECK_SCRIPT = """
local current_key = KEYS[1]
local previous_key = KEYS[2]
local window_seconds = tonumber(ARGV[1])
local limit = tonumber(ARGV[2])
local elapsed = tonumber(ARGV[3])

local current = tonumber(redis.call('GET', current_key) or '0')
local previous = tonumber(redis.call('GET', previous_key) or '0')
local previous_weight = 1.0 - (elapsed / window_seconds)
if previous_weight < 0 then previous_weight = 0 end
local weighted = current + math.floor(previous * previous_weight)
local retry_after = math.ceil(window_seconds - elapsed)
if retry_after < 1 then retry_after = 1 end

if weighted >= limit then
    return {weighted, retry_after, 0}
end

local new_current = redis.call('INCR', current_key)
if new_current == 1 then
    redis.call('EXPIRE', current_key, window_seconds * 2)
end
local weighted_after = new_current + math.floor(previous * previous_weight)
return {weighted_after, retry_after, 1}
"""

    def __init__(
        self,
        *,
        redis,
        limit: int,
        window_seconds: int = 60,
        prefix: str = "rate-limit",
        clock: Callable[[], float] | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds
        self.prefix = prefix
        self.clock = clock or monotonic

    async def check(self, key: str) -> RateLimitResult:
        now = self.clock()
        window_index = int(now // self.window_seconds)
        elapsed = now - window_index * self.window_seconds
        current_key = f"{self.prefix}:{key}:{window_index}"
        previous_key = f"{self.prefix}:{key}:{window_index - 1}"

        result = await self.redis.eval(
            self._CHECK_SCRIPT,
            2,
            current_key,
            previous_key,
            self.window_seconds,
            self.limit,
            elapsed,
        )
        weighted = int(result[0])
        retry_after = int(result[1])
        allowed = bool(int(result[2]))

        if not allowed:
            return RateLimitResult(
                allowed=False,
                remaining=0,
                retry_after_seconds=max(retry_after, 1),
            )
        return RateLimitResult(
            allowed=True,
            remaining=max(self.limit - weighted, 0),
        )
