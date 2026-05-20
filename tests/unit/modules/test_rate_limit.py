from app.modules.rate_limit.service import InMemoryRateLimiter, RedisRateLimiter


async def test_in_memory_rate_limiter_allows_until_limit():
    limiter = InMemoryRateLimiter(limit=2)

    first = await limiter.check("api-key-1")
    second = await limiter.check("api-key-1")
    third = await limiter.check("api-key-1")

    assert first.allowed
    assert second.allowed
    assert not third.allowed
    assert third.remaining == 0


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def incr(self, key: str) -> int:
        self.values[key] = self.values.get(key, 0) + 1
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> None:
        self.expirations[key] = seconds


async def test_redis_rate_limiter_sets_window_on_first_hit():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)

    result = await limiter.check("api-key-1")

    assert result.allowed
    assert result.remaining == 1
    assert redis.expirations["rate-limit:api-key-1"] == 60
