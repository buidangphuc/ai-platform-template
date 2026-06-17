from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.rate_limit.service import (
    InMemoryRateLimiter,
    RedisRateLimiter,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis


def build_principal_rate_limiter(
    settings: Settings,
    *,
    redis: Redis | None = None,
) -> InMemoryRateLimiter | RedisRateLimiter:
    return _build(
        backend=settings.RATE_LIMIT_BACKEND,
        limit=settings.RATE_LIMIT_PRINCIPAL_PER_MINUTE,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        redis=redis,
        prefix=f"{settings.RATE_LIMIT_REDIS_PREFIX}:principal",
    )


def build_ip_rate_limiter(
    settings: Settings,
    *,
    redis: Redis | None = None,
) -> InMemoryRateLimiter | RedisRateLimiter:
    return _build(
        backend=settings.RATE_LIMIT_BACKEND,
        limit=settings.RATE_LIMIT_IP_PER_MINUTE,
        window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        redis=redis,
        prefix=f"{settings.RATE_LIMIT_REDIS_PREFIX}:ip",
    )


def _build(
    *,
    backend: str,
    limit: int,
    window_seconds: int,
    redis: Redis | None,
    prefix: str,
) -> InMemoryRateLimiter | RedisRateLimiter:
    if backend == "memory":
        return InMemoryRateLimiter(limit=limit, window_seconds=window_seconds)
    if backend == "redis":
        if redis is None:
            raise RuntimeError("redis client is required for redis rate limit backend")
        return RedisRateLimiter(
            redis=redis,
            limit=limit,
            window_seconds=window_seconds,
            prefix=prefix,
        )
    raise ValueError(f"Unknown RATE_LIMIT_BACKEND={backend!r}")


class RateLimitAddon:
    name = "rate_limit"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RATE_LIMIT_ENABLED

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if settings.RATE_LIMIT_BACKEND == "redis" and not settings.REDIS_ENABLED:
            raise RuntimeError(
                "RateLimitAddon with RATE_LIMIT_BACKEND=redis requires REDIS_ENABLED"
            )
        if settings.RATE_LIMIT_PRINCIPAL_ENABLED:
            resources.principal_rate_limiter = build_principal_rate_limiter(
                settings, redis=resources.redis
            )
        if settings.RATE_LIMIT_IP_ENABLED:
            resources.ip_rate_limiter = build_ip_rate_limiter(
                settings, redis=resources.redis
            )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        resources.principal_rate_limiter = None
        resources.ip_rate_limiter = None
