import pytest
from fakeredis import aioredis

from app.modules.cache.adapters.redis import RedisCacheGateway
from app.modules.cache.gateway import CacheGateway

from .conformance import CacheGatewayConformance


class TestRedisCacheGateway(CacheGatewayConformance):
    @pytest.fixture
    def cache_factory(self):
        async def _build() -> CacheGateway:
            redis = aioredis.FakeRedis(decode_responses=False)
            return RedisCacheGateway(
                redis=redis,
                prefix="test",
                default_ttl_seconds=60,
            )

        return _build


async def test_redis_cache_prefixes_keys():
    redis = aioredis.FakeRedis(decode_responses=False)
    cache = RedisCacheGateway(redis=redis, prefix="prefix", default_ttl_seconds=60)

    await cache.set("key", b"value")

    assert await redis.get("prefix:key") == b"value"
