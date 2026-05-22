from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.bootstrap.state import attach_app_resource
from app.core.config import Settings
from app.modules.rate_limit.service import InMemoryRateLimiter, RedisRateLimiter

if TYPE_CHECKING:
    from redis.asyncio import Redis


def build_rate_limiter(
    settings: Settings,
    *,
    redis: Redis | None = None,
) -> InMemoryRateLimiter | RedisRateLimiter:
    if settings.RATE_LIMIT_BACKEND == "memory":
        return InMemoryRateLimiter(
            limit=settings.DEFAULT_RATE_LIMIT_PER_MINUTE,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        )

    if settings.RATE_LIMIT_BACKEND == "redis":
        if redis is None:
            raise RuntimeError("redis client is required for redis rate limit backend")
        return RedisRateLimiter(
            redis=redis,
            limit=settings.DEFAULT_RATE_LIMIT_PER_MINUTE,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
            prefix=settings.RATE_LIMIT_REDIS_PREFIX,
        )

    raise ValueError(f"Unknown RATE_LIMIT_BACKEND={settings.RATE_LIMIT_BACKEND!r}")


class RateLimitAddon:
    name = "rate_limit"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RATE_LIMIT_ENABLED

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ("redis",) if settings.RATE_LIMIT_BACKEND == "redis" else ()

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        attach_app_resource(
            app,
            resources,
            "rate_limiter",
            build_rate_limiter(settings, redis=resources.redis),
        )

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        return None
