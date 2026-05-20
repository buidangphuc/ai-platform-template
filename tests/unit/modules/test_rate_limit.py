import pytest

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


async def test_in_memory_rate_limiter_resets_after_window():
    now = 1000.0
    limiter = InMemoryRateLimiter(limit=1, window_seconds=60, clock=lambda: now)

    first = await limiter.check("api-key-1")
    second = await limiter.check("api-key-1")
    now += 60
    third = await limiter.check("api-key-1")

    assert first.allowed
    assert not second.allowed
    assert third.allowed
    assert third.remaining == 0


def test_in_memory_rate_limiter_rejects_invalid_limit():
    with pytest.raises(ValueError):
        InMemoryRateLimiter(limit=0)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}
        self.eval_calls: list[tuple[str, int, str, int, int]] = []

    async def eval(
        self,
        script: str,
        num_keys: int,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> int:
        self.eval_calls.append((script, num_keys, key, limit, window_seconds))
        self.values[key] = self.values.get(key, 0) + 1
        if self.values[key] == 1:
            self.expirations[key] = window_seconds
        return self.values[key]


async def test_redis_rate_limiter_sets_window_on_first_hit():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)

    result = await limiter.check("api-key-1")

    assert result.allowed
    assert result.remaining == 1
    assert redis.expirations["rate-limit:api-key-1"] == 60
    script, num_keys, key, limit, window_seconds = redis.eval_calls[0]
    assert "INCR" in script
    assert "EXPIRE" in script
    assert num_keys == 1
    assert key == "rate-limit:api-key-1"
    assert limit == 2
    assert window_seconds == 60
