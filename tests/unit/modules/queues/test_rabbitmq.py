"""RabbitMQ gateway against the real broker (``TEST_RABBITMQ_URL``)."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

import aio_pika
import pytest
from yarl import URL

from app.core.config import Settings
from app.modules.messaging.queue.adapters.rabbitmq import RabbitMQQueueGateway
from app.modules.messaging.queue.factory import open_queue_gateway
from tests.infra import require


@dataclass(frozen=True)
class _Topology:
    url: str
    queue: str
    exchange: str
    dead_queue: str


async def _cleanup(topology: _Topology) -> None:
    connection = await aio_pika.connect_robust(topology.url)
    try:
        channel = await connection.channel()
        await channel.queue_delete(topology.queue)
        await channel.queue_delete(topology.dead_queue)
        await channel.exchange_delete(topology.exchange)
    finally:
        await connection.close()


@pytest.fixture()
async def topology(
    rabbitmq_url: str, rabbitmq_queue_name: str
) -> AsyncIterator[_Topology]:
    value = _Topology(
        url=rabbitmq_url,
        queue=rabbitmq_queue_name,
        exchange=f"{rabbitmq_queue_name}.x",
        dead_queue=f"{rabbitmq_queue_name}.d",
    )
    try:
        yield value
    finally:
        await _cleanup(value)


@pytest.fixture()
def build_settings(
    infra_settings: Callable[..., Settings], topology: _Topology
) -> Callable[..., Settings]:
    def build(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "QUEUE_BACKEND": "rabbitmq",
            "RABBITMQ_URL": topology.url,
            "QUEUE_NAME": topology.queue,
            "RABBITMQ_DEAD_LETTER_EXCHANGE": topology.exchange,
            "RABBITMQ_DEAD_LETTER_QUEUE": topology.dead_queue,
        }
        values.update(overrides)
        return infra_settings(**values)

    return build


async def _open(settings: Settings) -> RabbitMQQueueGateway:
    gateway = await open_queue_gateway(settings, "rabbitmq")
    assert isinstance(gateway, RabbitMQQueueGateway)
    return gateway


async def _queue_depth(url: str, name: str) -> int:
    connection = await aio_pika.connect_robust(url)
    try:
        channel = await connection.channel()
        queue = await channel.declare_queue(name, passive=True)
        return queue.declaration_result.message_count or 0
    finally:
        await connection.close()


async def _wait_depth(url: str, name: str, expected: int) -> int:
    depth = -1
    for _ in range(40):
        depth = await _queue_depth(url, name)
        if depth == expected:
            break
        await asyncio.sleep(0.05)
    return depth


async def test_publish_then_consume_returns_the_message_and_ack_removes_it(
    build_settings, topology
):
    gateway = await _open(build_settings())
    try:
        await gateway.send({"hello": "world", "n": 1})
        received = await gateway.receive(max_messages=10, wait_seconds=2.0)

        assert [m.body for m in received] == [{"hello": "world", "n": 1}]
        assert received[0].receive_count == 1
        assert await _queue_depth(topology.url, topology.queue) == 0

        await gateway.ack(received[0])
        await gateway.ack(received[0])

        assert await gateway.receive(wait_seconds=0.3) == []
        assert await _wait_depth(topology.url, topology.queue, 0) == 0
    finally:
        await gateway.close()


async def _drop_broker_connections(container: str) -> None:
    process = await asyncio.create_subprocess_exec(
        "docker",
        "exec",
        container,
        "rabbitmqctl",
        "close_all_user_connections",
        "aipt",
        "test: broker dropped the connection",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    assert process.returncode == 0, stderr.decode()


async def test_gateway_reconnects_after_the_broker_drops_its_connection(
    build_settings,
):
    container = require("rabbitmq_container")
    gateway = await _open(build_settings())
    try:
        await gateway.send({"n": 1})
        await _drop_broker_connections(container)

        received: list = []
        for _ in range(30):
            try:
                await gateway.send({"n": 2})
                received = await gateway.receive(max_messages=10, wait_seconds=2.0)
                break
            except Exception:
                await asyncio.sleep(0.5)

        assert [m.body for m in received] == [{"n": 1}, {"n": 2}]
        for message in received:
            await gateway.ack(message)
    finally:
        await gateway.close()


async def test_receive_batches_up_to_max_messages(build_settings):
    gateway = await _open(build_settings())
    try:
        for n in range(3):
            await gateway.send({"n": n})
        first = await gateway.receive(max_messages=2, wait_seconds=2.0)
        rest = await gateway.receive(max_messages=2, wait_seconds=2.0)

        assert [m.body["n"] for m in first + rest] == [0, 1, 2]
        assert len(first) == 2
        assert len(rest) == 1
    finally:
        await gateway.close()


async def test_nack_without_requeue_lands_in_the_dead_letter_queue(
    build_settings, topology
):
    gateway = await _open(build_settings())
    try:
        await gateway.send({"poison": True})
        message = (await gateway.receive(max_messages=1, wait_seconds=2.0))[0]

        await gateway.nack(message, requeue=False)

        assert await _wait_depth(topology.url, topology.dead_queue, 1) == 1
        assert await _queue_depth(topology.url, topology.queue) == 0
        connection = await aio_pika.connect_robust(topology.url)
        try:
            channel = await connection.channel()
            dead = await channel.declare_queue(topology.dead_queue, passive=True)
            incoming = await dead.get(timeout=2, fail=True)
            await incoming.ack()
        finally:
            await connection.close()
        assert json.loads(incoming.body) == {"poison": True}
    finally:
        await gateway.close()


async def test_nack_without_requeue_drops_the_message_when_dead_letter_disabled(
    build_settings, topology
):
    gateway = await _open(build_settings(RABBITMQ_DEAD_LETTER_ENABLED=False))
    try:
        await gateway.send({"poison": True})
        message = (await gateway.receive(max_messages=1, wait_seconds=2.0))[0]

        await gateway.nack(message, requeue=False)

        assert await _wait_depth(topology.url, topology.queue, 0) == 0
        assert await gateway.receive(wait_seconds=0.3) == []
        with pytest.raises(aio_pika.exceptions.ChannelNotFoundEntity):
            await _queue_depth(topology.url, topology.dead_queue)
    finally:
        await gateway.close()


async def test_nack_with_requeue_redelivers_with_incremented_receive_count(
    build_settings,
):
    gateway = await _open(build_settings())
    try:
        await gateway.send({"retry": True})
        counts = []
        for _ in range(3):
            message = (await gateway.receive(max_messages=1, wait_seconds=2.0))[0]
            counts.append(message.receive_count)
            await gateway.nack(message, requeue=True)

        assert counts == [1, 2, 3]
    finally:
        await gateway.close()


async def test_unacked_message_is_redelivered_after_the_consumer_closes(
    build_settings,
):
    settings = build_settings()
    first = await _open(settings)
    await first.send({"job": 42})
    delivered = (await first.receive(max_messages=1, wait_seconds=2.0))[0]
    assert delivered.receive_count == 1
    await first.close()

    second = await _open(settings)
    try:
        redelivered = (await second.receive(max_messages=1, wait_seconds=2.0))[0]
        assert redelivered.body == {"job": 42}
        assert redelivered.receive_count == 2
        await second.ack(redelivered)
    finally:
        await second.close()


async def test_open_fails_with_a_clear_error_on_a_wrong_password(
    build_settings, topology
):
    bad_url = str(URL(topology.url).with_password(f"wrong-{uuid.uuid4().hex[:6]}"))

    with pytest.raises(aio_pika.exceptions.AMQPConnectionError) as error:
        async with asyncio.timeout(15):
            await open_queue_gateway(build_settings(RABBITMQ_URL=bad_url), "rabbitmq")

    assert "ACCESS_REFUSED" in str(error.value) or "auth" in str(error.value).lower()


async def test_open_fails_on_a_closed_port(build_settings, topology):
    closed_url = str(URL(topology.url).with_host("127.0.0.1").with_port(1))

    with pytest.raises(OSError):
        async with asyncio.timeout(15):
            await open_queue_gateway(
                build_settings(RABBITMQ_URL=closed_url), "rabbitmq"
            )


async def test_close_is_idempotent_and_releases_the_connection(build_settings):
    gateway = await _open(build_settings())
    connection = gateway._connection

    await gateway.close()
    await gateway.close()

    assert connection.is_closed


async def test_second_open_redeclares_the_same_topology(build_settings, topology):
    settings = build_settings()
    first = await _open(settings)
    await first.send({"kept": True})
    await first.close()

    second = await _open(settings)
    try:
        received = await second.receive(max_messages=1, wait_seconds=2.0)
        assert [m.body for m in received] == [{"kept": True}]
        await second.ack(received[0])
    finally:
        await second.close()


async def test_reopening_with_different_arguments_fails_and_releases_connection(
    build_settings,
):
    first = await _open(build_settings())
    try:
        with pytest.raises(aio_pika.exceptions.ChannelPreconditionFailed):
            await open_queue_gateway(
                build_settings(RABBITMQ_DEAD_LETTER_ENABLED=False), "rabbitmq"
            )
    finally:
        await first.close()


async def test_send_returns_the_id_the_receiver_sees(build_settings):
    gateway = await _open(build_settings())
    try:
        sent_id = await gateway.send({"a": 1})
        received = (await gateway.receive(max_messages=1, wait_seconds=2.0))[0]

        assert sent_id
        assert received.id == sent_id
        await gateway.nack(received, requeue=True)
        again = (await gateway.receive(max_messages=1, wait_seconds=2.0))[0]
        assert again.id == sent_id
    finally:
        await gateway.close()


async def test_close_before_open_is_a_no_op(build_settings):
    gateway = RabbitMQQueueGateway(url="amqp://unused", queue_name="unused")

    await gateway.close()


async def test_receive_waits_up_to_wait_seconds_on_an_empty_queue(build_settings):
    gateway = await _open(build_settings())
    try:
        started = time.monotonic()
        assert await gateway.receive(wait_seconds=0.5) == []
        assert time.monotonic() - started >= 0.45
    finally:
        await gateway.close()


async def test_receive_returns_a_message_published_during_the_wait(build_settings):
    gateway = await _open(build_settings())
    try:

        async def publish_later() -> None:
            await asyncio.sleep(0.3)
            await gateway.send({"late": True})

        publisher = asyncio.create_task(publish_later())
        started = time.monotonic()
        received = await gateway.receive(wait_seconds=3.0)
        elapsed = time.monotonic() - started
        await publisher

        assert [m.body for m in received] == [{"late": True}]
        assert elapsed < 2.0
        await gateway.ack(received[0])
    finally:
        await gateway.close()


async def test_nack_of_an_unknown_message_is_a_no_op(build_settings):
    gateway = await _open(build_settings())
    try:
        await gateway.send({"n": 1})
        [message] = await gateway.receive(wait_seconds=2.0)
        await gateway.ack(message)

        await gateway.nack(message)

        assert await gateway.receive(wait_seconds=0.2) == []
    finally:
        await gateway.close()
