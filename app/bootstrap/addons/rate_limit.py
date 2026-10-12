"""Lifecycle addon for rate_limit; bootstrap owns open/close."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.rate_limit.factory import (
    build_memory_rate_limiter,
    build_redis_rate_limiter,
)
from app.modules.platform.rate_limit.service import (
    InMemoryRateLimiter,
    RedisRateLimiter,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis


class RateLimitAddon:
    name = "rate_limit"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RATE_LIMIT_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if settings.RATE_LIMIT_PRINCIPAL_ENABLED:
            resources.principal_rate_limiter = _build_limiter(
                resources,
                settings,
                limit=settings.RATE_LIMIT_PRINCIPAL_PER_MINUTE,
                scope="principal",
            )
        if settings.RATE_LIMIT_IP_ENABLED:
            resources.ip_rate_limiter = _build_limiter(
                resources,
                settings,
                limit=settings.RATE_LIMIT_IP_PER_MINUTE,
                scope="ip",
            )

    async def close(self, resources: ApplicationResources) -> None:
        """Limiters hold no connection of their own (Redis is closed by its owner)."""


def _build_limiter(
    resources: ApplicationResources,
    settings: Settings,
    *,
    limit: int,
    scope: str,
) -> InMemoryRateLimiter | RedisRateLimiter:
    backend = settings.RATE_LIMIT_BACKEND
    if backend == "memory":
        return build_memory_rate_limiter(
            limit=limit,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        )
    if backend == "redis":
        return build_redis_rate_limiter(
            _redis(resources),
            limit=limit,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            prefix=f"{settings.RATE_LIMIT_REDIS_PREFIX}:{scope}",
        )
    raise ValueError(f"Unknown RATE_LIMIT_BACKEND={backend!r}")


def _redis(resources: ApplicationResources) -> Redis:
    if resources.redis is None:
        raise RuntimeError("RateLimitAddon needs an open Redis client")
    return resources.redis
