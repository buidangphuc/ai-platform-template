"""Lifecycle addon for cache: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.redis import build_redis_client
from app.modules.platform.cache.factory import build_redis_cache_gateway
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
        match settings.CACHE_BACKEND:
            case "redis":
                redis = build_redis_client(settings, decode_responses=False)
                stack.push_async_callback(redis.aclose)
                cache = build_redis_cache_gateway(settings, redis)
        stack.push_async_callback(cache.close)
        resources.cache = cache
