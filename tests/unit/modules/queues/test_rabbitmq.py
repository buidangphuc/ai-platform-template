"""RabbitMQ adapter redelivery behavior, against a fake ``aio_pika`` surface.

``aio_pika`` is an optional extra, so the module-level import is replaced with
a minimal fake; no broker is involved.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest

import app.modules.messaging.queue.adapters.rabbitmq as rabbitmq_mod
from app.modules.messaging.queue.adapters.rabbitmq import RabbitMQQueueGateway


class _Message:
    def __init__(self, body, delivery_mode=None, headers=None, message_id=None):
        self.body = body
        self.headers = headers or {}
        self.message_id = message_id
        self.delivery_tag = 1
        self.redelivered = False
        self.acked = False
        self.nack_requeue: bool | None = None

    async def ack(self) -> None:
        self.acked = True

    async def nack(self, requeue: bool = True) -> None:
        self.nack_requeue = requeue


class _Queue:
    def __init__(self, name: str, arguments: dict | None) -> None:
        self.name = name
        self.arguments = arguments
        self.items: list[_Message] = []
        self.bindings: list[tuple[Any, str]] = []

    async def get(self, timeout=None, fail=True):
        return self.items.pop(0) if self.items else None

    async def bind(self, exchange, routing_key: str) -> None:
        self.bindings.append((exchange, routing_key))


class _Channel:
    def __init__(self) -> None:
        self.queues: dict[str, _Queue] = {}
        self.exchanges: list[str] = []
        self.default_exchange = SimpleNamespace(publish=self._publish)

    async def set_qos(self, prefetch_count: int) -> None:
        return None

    async def declare_exchange(self, name, kind, durable=False):
        self.exchanges.append(name)
        return SimpleNamespace(name=name)

    async def declare_queue(self, name, durable=False, arguments=None):
        return self.queues.setdefault(name, _Queue(name, arguments))

    async def _publish(self, message: _Message, routing_key: str) -> None:
        self.queues[routing_key].items.append(message)


@pytest.fixture
def channel(monkeypatch) -> _Channel:
    chan = _Channel()

    class _Connection:
        async def channel(self):
            return chan

        async def close(self):
            return None

    async def connect_robust(url):
        return _Connection()

    fake = SimpleNamespace(
        Message=_Message,
        DeliveryMode=SimpleNamespace(PERSISTENT=2),
        ExchangeType=SimpleNamespace(DIRECT="direct"),
        connect_robust=connect_robust,
    )
    monkeypatch.setattr(rabbitmq_mod, "aio_pika", fake)
    return chan


def _gateway(**kwargs) -> RabbitMQQueueGateway:
    return RabbitMQQueueGateway(url="amqp://x", queue_name="work", **kwargs)


async def test_work_queue_declares_dead_letter_topology(channel):
    gateway = _gateway()
    await gateway.send({"a": 1})

    assert channel.exchanges == ["work.dlx"]
    assert channel.queues["work"].arguments == {
        "x-dead-letter-exchange": "work.dlx",
        "x-dead-letter-routing-key": "work",
    }
    assert channel.queues["work.dead"].bindings[0][1] == "work"


async def test_dead_letter_names_are_configurable_and_can_be_disabled(channel):
    custom = _gateway(dead_letter_exchange="X", dead_letter_queue="Q")
    await custom.send({"a": 1})
    assert channel.exchanges == ["X"]
    assert "Q" in channel.queues

    channel.queues.clear()
    channel.exchanges.clear()
    off = _gateway(dead_letter_enabled=False)
    await off.send({"a": 1})
    assert channel.exchanges == []
    assert channel.queues["work"].arguments is None


async def test_receive_count_increments_across_requeues(channel):
    gateway = _gateway()
    await gateway.send({"a": 1})

    counts = []
    for _ in range(3):
        message = (await gateway.receive(max_messages=1))[0]
        counts.append(message.receive_count)
        await gateway.nack(message, requeue=True)

    assert counts == [1, 2, 3]
    assert json.loads(channel.queues["work"].items[0].body) == {"a": 1}


async def test_requeue_republishes_and_acks_original(channel):
    gateway = _gateway()
    await gateway.send({"a": 1})
    message = (await gateway.receive(max_messages=1))[0]
    original = message.raw

    await gateway.nack(message, requeue=True)

    assert original.acked is True
    assert original.nack_requeue is None
    assert len(channel.queues["work"].items) == 1


async def test_nack_without_requeue_nacks_so_broker_dead_letters(channel):
    gateway = _gateway()
    await gateway.send({"a": 1})
    message = (await gateway.receive(max_messages=1))[0]

    await gateway.nack(message, requeue=False)

    assert message.raw.nack_requeue is False
    assert message.raw.acked is False
    assert channel.queues["work"].items == []


async def test_quorum_delivery_count_header_is_preferred_when_higher(channel):
    gateway = _gateway()
    await gateway.send({"a": 1})
    channel.queues["work"].items[0].headers = {"x-delivery-count": 4}

    message = (await gateway.receive(max_messages=1))[0]

    assert message.receive_count == 5


async def test_broker_redelivery_counts_as_second_attempt(channel):
    gateway = _gateway()
    await gateway.send({"a": 1})
    channel.queues["work"].items[0].redelivered = True

    assert (await gateway.receive(max_messages=1))[0].receive_count == 2
