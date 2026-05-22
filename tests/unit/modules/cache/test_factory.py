import pytest
from fakeredis import aioredis

from app.core.config import Settings
from app.modules.cache.adapters.memory import MemoryCacheGateway
from app.modules.cache.adapters.redis import RedisCacheGateway
from app.modules.cache.factory import CacheAddon, build_cache_gateway


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


def test_build_cache_gateway_defaults_to_memory():
    cache = build_cache_gateway(_settings())

    assert isinstance(cache, MemoryCacheGateway)


def test_build_cache_gateway_uses_redis_backend():
    redis = aioredis.FakeRedis(decode_responses=False)
    cache = build_cache_gateway(_settings(CACHE_BACKEND="redis"), redis=redis)

    assert isinstance(cache, RedisCacheGateway)


def test_redis_cache_requires_redis_client():
    with pytest.raises(RuntimeError, match="redis client"):
        build_cache_gateway(_settings(CACHE_BACKEND="redis"))


def test_cache_addon_is_enabled_only_by_flag():
    assert CacheAddon().is_enabled(_settings(CACHE_ENABLED=False)) is False
    assert CacheAddon().is_enabled(_settings(CACHE_ENABLED=True)) is True
