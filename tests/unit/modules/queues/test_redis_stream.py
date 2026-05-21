import pytest
from fakeredis import aioredis

from app.modules.queue.adapters.redis_stream import RedisStreamQueueGateway
from app.modules.queue.gateway import QueueGateway

from .conformance import QueueGatewayConformance


class TestRedisStreamQueueGateway(QueueGatewayConformance):
    @pytest.fixture
    def gateway_factory(self):
        async def _build() -> QueueGateway:
            redis = aioredis.FakeRedis(decode_responses=True)
            return RedisStreamQueueGateway(
                redis=redis,
                stream=f"test-stream-{id(redis)}",
                consumer_group=f"workers-{id(redis)}",
            )

        return _build
