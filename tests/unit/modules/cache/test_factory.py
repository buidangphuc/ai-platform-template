from collections.abc import Callable

import pytest
from pydantic import ValidationError
from redis.asyncio import Redis

from app.bootstrap.addons.cache import CacheAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.cache.adapters.redis import RedisCacheGateway
from app.modules.platform.cache.factory import build_redis_cache_gateway
from tests.factories import build_test_settings, open_addon


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def test_build_redis_cache_gateway_uses_settings(
    redis_client: Redis, redis_prefix: str
):
    cache = build_redis_cache_gateway(
        _settings(CACHE_BACKEND="redis", CACHE_PREFIX=redis_prefix), redis_client
    )

    assert isinstance(cache, RedisCacheGateway)
    assert cache.prefix == redis_prefix


async def test_cache_addon_opens_the_redis_backend_and_closes_gateway(
    redis_client: Redis,
    redis_prefix: str,
    infra_settings: Callable[..., Settings],
):
    resources = ApplicationResources()
    addon = CacheAddon()

    stack = await open_addon(
        addon,
        resources,
        infra_settings(
            CACHE_ENABLED=True,
            CACHE_BACKEND="redis",
            CACHE_PREFIX=redis_prefix,
            REDIS_ENABLED=True,
        ),
    )
    assert isinstance(resources.cache, RedisCacheGateway)
    await resources.cache.set("k", b"v")
    assert await redis_client.get(f"{redis_prefix}:k") == b"v"
    await stack.aclose()


def test_settings_reject_unknown_cache_backend():
    with pytest.raises(ValidationError, match="CACHE_BACKEND"):
        _settings(CACHE_BACKEND="bogus")


def test_cache_addon_is_enabled_only_by_flag():
    assert CacheAddon().is_enabled(_settings(CACHE_ENABLED=False)) is False
    assert (
        CacheAddon().is_enabled(_settings(CACHE_ENABLED=True, REDIS_ENABLED=True))
        is True
    )


async def test_cache_addon_round_trips_non_utf8_bytes(
    redis_client: Redis,
    redis_prefix: str,
    infra_settings: Callable[..., Settings],
):
    resources = ApplicationResources()
    payloads = {"a": b"\xff\xfe\x00\x80", "b": bytes(range(256))}

    stack = await open_addon(
        CacheAddon(),
        resources,
        infra_settings(
            CACHE_ENABLED=True,
            CACHE_BACKEND="redis",
            CACHE_PREFIX=redis_prefix,
            REDIS_ENABLED=True,
        ),
    )
    try:
        assert resources.cache is not None
        await resources.cache.set_many(payloads)

        assert await resources.cache.get("a") == payloads["a"]
        assert await resources.cache.get_many(["a", "b"]) == payloads
    finally:
        await stack.aclose()
