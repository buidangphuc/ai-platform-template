import asyncio
import json

import pytest
from redis.asyncio import Redis

from app.modules.messaging.queue.adapters.redis_stream import RedisStreamQueueGateway
from app.modules.messaging.queue.gateway import QueueGateway

from .conformance import QueueGatewayConformance

pytestmark = pytest.mark.parametrize("redis_client", [True], indirect=True)


class TestRedisStreamQueueGateway(QueueGatewayConformance):
    @pytest.fixture
    def gateway_factory(self, redis_client: Redis, redis_prefix: str):
        async def _build() -> QueueGateway:
            return RedisStreamQueueGateway(
                redis=redis_client,
                stream=f"{redis_prefix}:stream",
                consumer_group="workers",
            )

        return _build


def _gateway(redis: Redis, prefix: str, **kwargs) -> RedisStreamQueueGateway:
    return RedisStreamQueueGateway(
        redis=redis,
        stream=f"{prefix}:s",
        consumer_group="workers",
        min_idle_seconds=0.01,
        **kwargs,
    )


async def test_requeue_keeps_message_id_and_increments_receive_count(
    redis_client: Redis, redis_prefix: str
):
    gateway = _gateway(redis_client, redis_prefix, consumer_name="c1")
    await gateway.send({"value": 1})

    first = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]
    await gateway.nack(first, requeue=True)
    second = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]
    await gateway.nack(second, requeue=True)
    third = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]

    assert first.receive_count == 1
    assert first.receive_count < second.receive_count < third.receive_count
    assert second.id == first.id == third.id
    assert second.body == {"value": 1}


async def test_crashed_consumer_pending_entry_is_reclaimed_after_min_idle(
    redis_client: Redis, redis_prefix: str
):
    crashed = _gateway(redis_client, redis_prefix, consumer_name="dead-pod")
    survivor = _gateway(redis_client, redis_prefix, consumer_name="live-pod")
    await crashed.send({"value": 1})
    await crashed.receive(max_messages=1, wait_seconds=1.0)  # never acked

    await asyncio.sleep(0.05)
    reclaimed = await survivor.receive(max_messages=1, wait_seconds=0.1)

    assert [m.body for m in reclaimed] == [{"value": 1}]
    assert reclaimed[0].receive_count == 2


async def test_entry_is_not_reclaimed_before_min_idle(
    redis_client: Redis, redis_prefix: str
):
    gateway = RedisStreamQueueGateway(
        redis=redis_client,
        stream=f"{redis_prefix}:s",
        consumer_group="workers",
        min_idle_seconds=60,
    )
    await gateway.send({"value": 1})
    await gateway.receive(max_messages=1, wait_seconds=1.0)

    assert await gateway.receive(max_messages=1, wait_seconds=0.1) == []


async def test_nack_without_requeue_moves_entry_to_dead_stream(
    redis_client: Redis, redis_prefix: str
):
    gateway = _gateway(redis_client, redis_prefix, consumer_name="c1")
    await gateway.send({"value": 1})
    message = (await gateway.receive(max_messages=1, wait_seconds=1.0))[0]

    await gateway.nack(message, requeue=False)

    dead = await redis_client.xrange(f"{redis_prefix}:s:dead")
    assert len(dead) == 1
    assert json.loads(dead[0][1]["body"]) == {"value": 1}
    assert dead[0][1]["original_message_id"] == message.id
    assert (await redis_client.xpending(f"{redis_prefix}:s", "workers"))["pending"] == 0


async def test_entry_over_max_deliveries_is_dead_lettered_on_reclaim(
    redis_client: Redis, redis_prefix: str
):
    gateway = _gateway(redis_client, redis_prefix, consumer_name="c1", max_deliveries=2)
    await gateway.send({"value": 1})
    await gateway.receive(max_messages=1, wait_seconds=1.0)  # delivery 1, crash

    for _ in range(2):  # reclaim -> delivery 2 (ok), then 3 (> max)
        await asyncio.sleep(0.05)
        reclaimed = await gateway.receive(max_messages=1, wait_seconds=0.1)

    assert reclaimed == []
    dead = await redis_client.xrange(f"{redis_prefix}:s:dead")
    assert len(dead) == 1
    assert dead[0][1]["reason"] == "max_deliveries"
    assert dead[0][1]["receive_count"] == "3"
    assert (await redis_client.xpending(f"{redis_prefix}:s", "workers"))["pending"] == 0


async def test_consumer_name_is_stable_from_hostname(
    monkeypatch, redis_client: Redis, redis_prefix: str
):
    monkeypatch.setenv("HOSTNAME", "pod-7")
    assert _gateway(redis_client, redis_prefix).consumer_name == "pod-7"
    assert (
        _gateway(redis_client, redis_prefix, consumer_name="explicit").consumer_name
        == "explicit"
    )
    monkeypatch.delenv("HOSTNAME")
    assert _gateway(redis_client, redis_prefix).consumer_name.startswith("worker-")


async def test_ack_removes_the_entry_so_the_stream_does_not_grow(
    redis_client: Redis, redis_prefix: str
):
    gateway = _gateway(redis_client, redis_prefix, consumer_name="c1")
    for value in range(3):
        await gateway.send({"value": value})
    for message in await gateway.receive(max_messages=3, wait_seconds=1.0):
        await gateway.ack(message)

    assert await redis_client.xlen(f"{redis_prefix}:s") == 0


async def test_dead_lettering_removes_the_entry_and_caps_the_dead_stream(
    redis_client: Redis, redis_prefix: str
):
    gateway = _gateway(
        redis_client, redis_prefix, consumer_name="c1", dead_letter_maxlen=2
    )
    for value in range(3):
        await gateway.send({"value": value})
    for message in await gateway.receive(max_messages=3, wait_seconds=1.0):
        await gateway.nack(message, requeue=False)

    assert await redis_client.xlen(f"{redis_prefix}:s") == 0
    dead = await redis_client.xrange(f"{redis_prefix}:s:dead")
    assert [json.loads(fields["body"])["value"] for _, fields in dead] == [1, 2]
