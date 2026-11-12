import pytest
from redis.asyncio import Redis

from app.modules.platform.cache.adapters.redis import RedisCacheGateway
from app.modules.platform.cache.gateway import CacheGateway

from .conformance import CacheGatewayConformance


class TestRedisCacheGateway(CacheGatewayConformance):
    @pytest.fixture
    def cache_factory(self, redis_client: Redis, redis_prefix: str):
        async def _build() -> CacheGateway:
            return RedisCacheGateway(
                redis=redis_client,
                prefix=redis_prefix,
                default_ttl_seconds=60,
            )

        return _build


async def test_redis_cache_prefixes_keys(redis_client: Redis, redis_prefix: str):
    cache = RedisCacheGateway(
        redis=redis_client, prefix=redis_prefix, default_ttl_seconds=60
    )

    await cache.set("key", b"value")

    assert await redis_client.get(f"{redis_prefix}:key") == b"value"
