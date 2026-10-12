"""Lifecycle addon for cache; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.cache.factory import build_cache_gateway


class CacheAddon:
    name = "cache"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.CACHE_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if settings.CACHE_BACKEND == "redis" and not settings.REDIS_ENABLED:
            raise RuntimeError(
                "CacheAddon with CACHE_BACKEND=redis requires REDIS_ENABLED"
            )
        resources.cache = build_cache_gateway(settings, redis=resources.redis)

    async def close(self, resources: ApplicationResources) -> None:
        if resources.cache is not None:
            await resources.cache.close()
            resources.cache = None
