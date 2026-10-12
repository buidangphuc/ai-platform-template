"""Lifecycle addon for rate_limit: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources, opened
from app.core.config import Settings
from app.modules.platform.rate_limit.factory import (
    build_memory_rate_limiter,
    build_redis_rate_limiter,
)
from app.modules.platform.rate_limit.service import (
    InMemoryRateLimiter,
    RedisRateLimiter,
)


class RateLimitAddon:
    name = "rate_limit"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RATE_LIMIT_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        # Limiters hold no connection of their own; Redis is closed by its owner.
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
            opened(resources.redis, "redis"),
            limit=limit,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            prefix=f"{settings.RATE_LIMIT_REDIS_PREFIX}:{scope}",
        )
    raise ValueError(f"Unknown RATE_LIMIT_BACKEND={backend!r}")
