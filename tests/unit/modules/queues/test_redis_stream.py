import asyncio
import json

import pytest
from fakeredis import aioredis

from app.modules.messaging.queue.adapters.redis_stream import RedisStreamQueueGateway
from app.modules.messaging.queue.gateway import QueueGateway

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


def _gateway(redis, **kwargs) -> RedisStreamQueueGateway:
    return RedisStreamQueueGateway(
        redis=redis,
        stream="s",
        consumer_group="workers",
        min_idle_seconds=0.01,
        **kwargs,
    )


async def test_requeue_keeps_message_id_and_increments_receive_count():
    redis = aioredis.FakeRedis(decode_responses=True)
    gateway = _gateway(redis, consumer_name="c1")
    await gateway.send({"value": 1})

    first = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]
    await gateway.nack(first, requeue=True)
    second = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]
    await gateway.nack(second, requeue=True)
    third = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]

    # fakeredis bumps the delivery counter on XCLAIM JUSTID (real Redis does not;
    # verified [1, 2, 3] against redis:7), so only assert strict growth here.
    assert first.receive_count == 1
    assert first.receive_count < second.receive_count < third.receive_count
    assert second.id == first.id == third.id
    assert second.body == {"value": 1}


async def test_crashed_consumer_pending_entry_is_reclaimed_after_min_idle():
    redis = aioredis.FakeRedis(decode_responses=True)
    crashed = _gateway(redis, consumer_name="dead-pod")
    survivor = _gateway(redis, consumer_name="live-pod")
    await crashed.send({"value": 1})
    await crashed.receive(max_messages=1, wait_seconds=1.0)  # never acked

    await asyncio.sleep(0.05)
    reclaimed = await survivor.receive(max_messages=1, wait_seconds=0.1)

    assert [m.body for m in reclaimed] == [{"value": 1}]
    assert reclaimed[0].receive_count == 2


async def test_entry_is_not_reclaimed_before_min_idle():
    redis = aioredis.FakeRedis(decode_responses=True)
    gateway = RedisStreamQueueGateway(
        redis=redis, stream="s", consumer_group="workers", min_idle_seconds=60
    )
    await gateway.send({"value": 1})
    await gateway.receive(max_messages=1, wait_seconds=1.0)

    assert await gateway.receive(max_messages=1, wait_seconds=0.1) == []


async def test_nack_without_requeue_moves_entry_to_dead_stream():
    redis = aioredis.FakeRedis(decode_responses=True)
    gateway = _gateway(redis, consumer_name="c1")
    await gateway.send({"value": 1})
    message = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]

    await gateway.nack(message, requeue=False)

    dead = await redis.xrange("s:dead")
    assert len(dead) == 1
    assert json.loads(dead[0][1]["body"]) == {"value": 1}
    assert dead[0][1]["original_message_id"] == message.id
    assert (await redis.xpending("s", "workers"))["pending"] == 0


async def test_entry_over_max_deliveries_is_dead_lettered_on_reclaim():
    redis = aioredis.FakeRedis(decode_responses=True)
    gateway = _gateway(redis, consumer_name="c1", max_deliveries=2)
    await gateway.send({"value": 1})
    await gateway.receive(max_messages=1, wait_seconds=1.0)  # delivery 1, crash

    for _ in range(2):  # reclaim -> delivery 2 (ok), then 3 (> max)
        await asyncio.sleep(0.05)
        reclaimed = await gateway.receive(max_messages=1, wait_seconds=0.1)

    assert reclaimed == []
    dead = await redis.xrange("s:dead")
    assert len(dead) == 1
    assert dead[0][1]["reason"] == "max_deliveries"
    assert dead[0][1]["receive_count"] == "3"
    assert (await redis.xpending("s", "workers"))["pending"] == 0


async def test_consumer_name_is_stable_from_hostname(monkeypatch):
    redis = aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setenv("HOSTNAME", "pod-7")
    assert _gateway(redis).consumer_name == "pod-7"
    assert _gateway(redis, consumer_name="explicit").consumer_name == "explicit"
    monkeypatch.delenv("HOSTNAME")
    assert _gateway(redis).consumer_name.startswith("worker-")
