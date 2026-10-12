"""Lifecycle addon for cache; bootstrap owns open/close."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.cache.factory import (
    build_memory_cache_gateway,
    build_redis_cache_gateway,
)
from app.modules.platform.cache.gateway import CacheGateway

if TYPE_CHECKING:
    from redis.asyncio import Redis


class CacheAddon:
    name = "cache"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.CACHE_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        backend = settings.CACHE_BACKEND
        if backend == "memory":
            resources.cache = build_memory_cache_gateway(settings)
        elif backend == "redis":
            resources.cache = build_redis_cache_gateway(settings, _redis(resources))
        else:
            raise ValueError(f"Unknown CACHE_BACKEND={backend!r}")

    async def close(self, resources: ApplicationResources) -> None:
        await _cache(resources).close()


def _redis(resources: ApplicationResources) -> Redis:
    if resources.redis is None:
        raise RuntimeError("CacheAddon needs an open Redis client")
    return resources.redis


def _cache(resources: ApplicationResources) -> CacheGateway:
    if resources.cache is None:
        raise RuntimeError("CacheAddon has no open cache gateway")
    return resources.cache
