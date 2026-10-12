from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.platform.cache.gateway import CacheGateway

if TYPE_CHECKING:
    from redis.asyncio import Redis


def build_memory_cache_gateway(settings: Settings) -> CacheGateway:
    from app.modules.platform.cache.adapters.memory import MemoryCacheGateway

    return MemoryCacheGateway(
        prefix=settings.CACHE_PREFIX,
        default_ttl_seconds=settings.CACHE_DEFAULT_TTL_SECONDS,
    )


def build_redis_cache_gateway(settings: Settings, redis: Redis) -> CacheGateway:
    from app.modules.platform.cache.adapters.redis import RedisCacheGateway

    return RedisCacheGateway(
        redis=redis,
        prefix=settings.CACHE_PREFIX,
        default_ttl_seconds=settings.CACHE_DEFAULT_TTL_SECONDS,
    )
