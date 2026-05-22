from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import attach_app_resource, optional_app_resource
from app.core.config import Settings
from app.modules.cache.gateway import CacheGateway

if TYPE_CHECKING:
    from redis.asyncio import Redis


def build_cache_gateway(
    settings: Settings,
    *,
    redis: Redis | None = None,
) -> CacheGateway:
    if settings.CACHE_BACKEND == "memory":
        from app.modules.cache.adapters.memory import MemoryCacheGateway

        return MemoryCacheGateway(
            prefix=settings.CACHE_PREFIX,
            default_ttl_seconds=settings.CACHE_DEFAULT_TTL_SECONDS,
        )

    if settings.CACHE_BACKEND == "redis":
        if redis is None:
            raise RuntimeError("redis client is required for redis cache backend")
        from app.modules.cache.adapters.redis import RedisCacheGateway

        return RedisCacheGateway(
            redis=redis,
            prefix=settings.CACHE_PREFIX,
            default_ttl_seconds=settings.CACHE_DEFAULT_TTL_SECONDS,
        )

    raise ValueError(f"Unknown CACHE_BACKEND={settings.CACHE_BACKEND!r}")


class CacheAddon:
    name = "cache"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.CACHE_ENABLED

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ("redis",) if settings.CACHE_BACKEND == "redis" else ()

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        cache = build_cache_gateway(settings, redis=resources.redis)
        attach_app_resource(app, resources, "cache", cache)

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        cache = optional_app_resource(app, "cache")
        if cache is not None:
            await cache.close()
