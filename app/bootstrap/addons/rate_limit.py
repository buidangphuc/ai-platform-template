"""Lifecycle addon for rate_limit; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.rate_limit.factory import (
    build_ip_rate_limiter,
    build_principal_rate_limiter,
)


class RateLimitAddon:
    name = "rate_limit"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.RATE_LIMIT_ENABLED

    async def open(
        self,
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

    async def close(self, resources: ApplicationResources) -> None:
        resources.principal_rate_limiter = None
        resources.ip_rate_limiter = None
