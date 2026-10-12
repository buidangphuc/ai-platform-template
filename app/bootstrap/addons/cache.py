"""Lifecycle addon for cache: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources, opened
from app.core.config import Settings
from app.modules.platform.cache.factory import (
    build_memory_cache_gateway,
    build_redis_cache_gateway,
)
from app.modules.platform.cache.gateway import CacheGateway


class CacheAddon:
    name = "cache"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.CACHE_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        cache: CacheGateway
        backend = settings.CACHE_BACKEND
        if backend == "memory":
            cache = build_memory_cache_gateway(settings)
        elif backend == "redis":
            cache = build_redis_cache_gateway(
                settings, opened(resources.redis, "redis")
            )
        else:
            raise ValueError(f"Unknown CACHE_BACKEND={backend!r}")
        stack.push_async_callback(cache.close)
        resources.cache = cache
