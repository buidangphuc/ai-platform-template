from __future__ import annotations

from typing import TYPE_CHECKING

from app.modules.platform.rate_limit.service import (
    InMemoryRateLimiter,
    RedisRateLimiter,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis


def build_memory_rate_limiter(
    *, limit: int, window_seconds: int
) -> InMemoryRateLimiter:
    return InMemoryRateLimiter(limit=limit, window_seconds=window_seconds)


def build_redis_rate_limiter(
    redis: Redis,
    *,
    limit: int,
    window_seconds: int,
    prefix: str,
) -> RedisRateLimiter:
    return RedisRateLimiter(
        redis=redis,
        limit=limit,
        window_seconds=window_seconds,
        prefix=prefix,
    )
