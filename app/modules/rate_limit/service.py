from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    remaining: int


class InMemoryRateLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._counts: dict[str, int] = {}

    async def check(self, key: str) -> RateLimitResult:
        count = self._counts.get(key, 0) + 1
        self._counts[key] = count
        remaining = max(self.limit - count, 0)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)


class RedisRateLimiter:
    def __init__(self, *, redis, limit: int, window_seconds: int = 60) -> None:
        self.redis = redis
        self.limit = limit
        self.window_seconds = window_seconds

    async def check(self, key: str) -> RateLimitResult:
        redis_key = f"rate-limit:{key}"
        count = await self.redis.incr(redis_key)
        if count == 1:
            await self.redis.expire(redis_key, self.window_seconds)
        remaining = max(self.limit - count, 0)
        return RateLimitResult(allowed=count <= self.limit, remaining=remaining)
