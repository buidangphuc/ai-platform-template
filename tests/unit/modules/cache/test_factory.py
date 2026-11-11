import pytest
from pydantic import ValidationError
from redis.asyncio import Redis

from app.bootstrap.addons.cache import CacheAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.cache.adapters.memory import MemoryCacheGateway
from app.modules.platform.cache.adapters.redis import RedisCacheGateway
from app.modules.platform.cache.factory import (
    build_memory_cache_gateway,
    build_redis_cache_gateway,
)
from tests.factories import build_test_settings, open_addon


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def test_build_memory_cache_gateway_uses_settings():
    cache = build_memory_cache_gateway(_settings())

    assert isinstance(cache, MemoryCacheGateway)


def test_build_redis_cache_gateway_uses_settings(
    redis_client: Redis, redis_prefix: str
):
    cache = build_redis_cache_gateway(
        _settings(CACHE_BACKEND="redis", CACHE_PREFIX=redis_prefix), redis_client
    )

    assert isinstance(cache, RedisCacheGateway)
    assert cache.prefix == redis_prefix


async def test_cache_addon_selects_backend_and_closes_gateway(
    redis_client: Redis, redis_prefix: str
):
    resources = ApplicationResources(redis=redis_client)
    addon = CacheAddon()

    stack = await open_addon(addon, resources, _settings(CACHE_ENABLED=True))
    assert isinstance(resources.cache, MemoryCacheGateway)
    await stack.aclose()

    stack = await open_addon(
        addon,
        resources,
        _settings(
            CACHE_ENABLED=True,
            CACHE_BACKEND="redis",
            CACHE_PREFIX=redis_prefix,
            REDIS_ENABLED=True,
        ),
    )
    assert isinstance(resources.cache, RedisCacheGateway)
    await resources.cache.set("k", b"v")
    assert await redis_client.get(f"{redis_prefix}:k") == b"v"


def test_settings_reject_unknown_cache_backend():
    with pytest.raises(ValidationError, match="CACHE_BACKEND"):
        _settings(CACHE_BACKEND="bogus")


def test_cache_addon_is_enabled_only_by_flag():
    assert CacheAddon().is_enabled(_settings(CACHE_ENABLED=False)) is False
    assert CacheAddon().is_enabled(_settings(CACHE_ENABLED=True)) is True
