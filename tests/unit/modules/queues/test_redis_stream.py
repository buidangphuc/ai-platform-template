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


async def test_redis_stream_requeue_preserves_original_message_id():
    redis = aioredis.FakeRedis(decode_responses=True)
    gateway = RedisStreamQueueGateway(
        redis=redis,
        stream=f"test-stream-{id(redis)}",
        consumer_group=f"workers-{id(redis)}",
    )
    await gateway.send({"value": 1})

    first = await gateway.receive(max_messages=1, wait_seconds=1.0)
    await gateway.nack(first[0], requeue=True)
    second = await gateway.receive(max_messages=1, wait_seconds=1.0)

    assert second[0].body["value"] == 1
    assert second[0].body["original_message_id"] == first[0].id
