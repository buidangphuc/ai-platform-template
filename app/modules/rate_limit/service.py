from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int


class InMemoryRateLimiter:
    def __init__(
        self,
        limit: int,
        window_seconds: int = 60,
        clock: Callable[[], float] | None = None,
    ) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.limit = limit
        self.window_seconds = window_seconds
        self.clock = clock or monotonic
        self._counts: dict[str, tuple[int, float]] = {}

    async def check(self, key: str) -> RateLimitResult:
        now = self.clock()
        count, started_at = self._counts.get(key, (0, now))
        if now - started_at >= self.window_seconds:
            count = 0
            started_at = now

        count += 1
        self._counts[key] = (count, started_at)
        remaining = max(self.limit - count, 0)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)


class RedisRateLimiter:
    _CHECK_SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
    redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return current
"""

    def __init__(self, *, redis, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        redis_key = f"rate-limit:{key}"
        count = await self.redis.eval(
            self._CHECK_SCRIPT,
            1,
            redis_key,
            self.window_seconds,
        )
        count = int(count)
        remaining = max(self.limit - count, 0)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)
