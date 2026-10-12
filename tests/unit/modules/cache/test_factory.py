import pytest
from fakeredis import aioredis

from app.bootstrap.addons.cache import CacheAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.cache.adapters.memory import MemoryCacheGateway
from app.modules.platform.cache.adapters.redis import RedisCacheGateway
from app.modules.platform.cache.factory import (
    build_memory_cache_gateway,
    build_redis_cache_gateway,
)
from tests.factories import build_test_settings


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def test_build_memory_cache_gateway_uses_settings():
    cache = build_memory_cache_gateway(_settings())

    assert isinstance(cache, MemoryCacheGateway)


def test_build_redis_cache_gateway_uses_settings():
    redis = aioredis.FakeRedis(decode_responses=False)
    cache = build_redis_cache_gateway(_settings(CACHE_BACKEND="redis"), redis)

    assert isinstance(cache, RedisCacheGateway)


async def test_cache_addon_selects_backend_and_closes_gateway():
    resources = ApplicationResources(redis=aioredis.FakeRedis(decode_responses=False))
    addon = CacheAddon()

    await addon.open(resources, _settings(CACHE_ENABLED=True))
    assert isinstance(resources.cache, MemoryCacheGateway)
    await addon.close(resources)

    await addon.open(
        resources,
        _settings(CACHE_ENABLED=True, CACHE_BACKEND="redis", REDIS_ENABLED=True),
    )
    assert isinstance(resources.cache, RedisCacheGateway)


async def test_cache_addon_rejects_unknown_backend():
    with pytest.raises(ValueError, match="Unknown CACHE_BACKEND"):
        await CacheAddon().open(
            ApplicationResources(), _settings(CACHE_BACKEND="bogus")
        )


def test_cache_addon_is_enabled_only_by_flag():
    assert CacheAddon().is_enabled(_settings(CACHE_ENABLED=False)) is False
    assert CacheAddon().is_enabled(_settings(CACHE_ENABLED=True)) is True
