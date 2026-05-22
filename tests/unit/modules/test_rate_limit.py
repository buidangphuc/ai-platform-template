import pytest
from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.rate_limit.factory import RateLimitAddon, build_rate_limiter
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
        self.eval_calls: list[tuple[str, int, str, int]] = []

    async def eval(
        self,
        script: str,
        num_keys: int,
        key: str,
        window_seconds: int,
    ) -> str:
        self.eval_calls.append((script, num_keys, key, window_seconds))
        self.values[key] = self.values.get(key, 0) + 1
        if self.values[key] == 1:
            self.expirations[key] = window_seconds
        return str(self.values[key])


async def test_redis_rate_limiter_sets_window_on_first_hit():
    redis = FakeRedis()
    limiter = RedisRateLimiter(redis=redis, limit=2, window_seconds=60)

    result = await limiter.check("api-key-1")

    assert result.allowed
    assert result.remaining == 1
    assert redis.expirations["rate-limit:api-key-1"] == 60
    script, num_keys, key, window_seconds = redis.eval_calls[0]
    assert "INCR" in script
    assert "EXPIRE" in script
    assert num_keys == 1
    assert key == "rate-limit:api-key-1"
    assert window_seconds == 60


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
    }
    base.update(overrides)
    return Settings(**base)


def test_build_rate_limiter_defaults_to_memory():
    limiter = build_rate_limiter(_settings(DEFAULT_RATE_LIMIT_PER_MINUTE=5))

    assert isinstance(limiter, InMemoryRateLimiter)
    assert limiter.limit == 5


def test_build_rate_limiter_uses_redis_backend():
    redis = FakeRedis()
    limiter = build_rate_limiter(_settings(RATE_LIMIT_BACKEND="redis"), redis=redis)

    assert isinstance(limiter, RedisRateLimiter)


def test_redis_rate_limiter_requires_redis_client():
    with pytest.raises(RuntimeError, match="redis client"):
        build_rate_limiter(_settings(RATE_LIMIT_BACKEND="redis"))


async def test_rate_limit_addon_attaches_limiter_when_enabled():
    app = FastAPI()
    resources = ApplicationResources(redis=FakeRedis())
    addon = RateLimitAddon()

    await addon.open(app, resources, _settings(RATE_LIMIT_BACKEND="redis"))

    assert isinstance(app.state.rate_limiter, RedisRateLimiter)


def test_rate_limit_addon_respects_enabled_flag():
    addon = RateLimitAddon()

    assert addon.is_enabled(_settings(RATE_LIMIT_ENABLED=True)) is True
    assert addon.is_enabled(_settings(RATE_LIMIT_ENABLED=False)) is False
