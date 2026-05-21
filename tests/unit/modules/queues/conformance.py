"""Shared conformance contract every QueueGateway adapter must satisfy.

Concrete test files instantiate ``QueueGatewayConformance`` with a fixture
that builds the adapter under test. Pytest collects subclass tests so SQS,
Redis Streams, RabbitMQ, etc. only need a 5-line wrapper.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable

import pytest

from app.modules.queue.gateway import QueueGateway

GatewayFactory = Callable[[], Awaitable[QueueGateway]]


class QueueGatewayConformance:
    """Subclass and set ``gateway_factory`` fixture to validate an adapter."""

    @pytest.fixture
    async def gateway(
        self, gateway_factory: GatewayFactory
    ) -> AsyncIterator[QueueGateway]:
        instance = await gateway_factory()
        try:
            yield instance
        finally:
            await instance.close()

    async def test_send_then_receive_round_trip(self, gateway: QueueGateway):
        message_id = await gateway.send({"hello": "world"})
        messages = await gateway.receive(max_messages=1, wait_seconds=1.0)

        assert len(messages) == 1
        assert messages[0].body == {"hello": "world"}
        assert messages[0].id  # backend may rewrite, just require non-empty
        assert message_id

    async def test_receive_returns_empty_when_no_messages(self, gateway: QueueGateway):
        messages = await gateway.receive(max_messages=5, wait_seconds=0.1)
        assert messages == []

    async def test_ack_removes_message_from_inflight(self, gateway: QueueGateway):
        await gateway.send({"key": "value"})
        messages = await gateway.receive(max_messages=1, wait_seconds=1.0)
        assert len(messages) == 1
        await gateway.ack(messages[0])

        leftover = await gateway.receive(max_messages=1, wait_seconds=0.1)
        assert leftover == []

    async def test_nack_with_requeue_makes_message_redeliverable(
        self, gateway: QueueGateway
    ):
        await gateway.send({"k": "v"})

        first = await gateway.receive(max_messages=1, wait_seconds=1.0)
        assert len(first) == 1
        await gateway.nack(first[0], requeue=True)

        second = await gateway.receive(max_messages=1, wait_seconds=1.0)
        assert len(second) == 1
        assert second[0].body == {"k": "v"}

    async def test_receive_returns_up_to_max_messages(self, gateway: QueueGateway):
        for index in range(3):
            await gateway.send({"i": index})

        messages = await gateway.receive(max_messages=2, wait_seconds=1.0)
        assert len(messages) == 2

    async def test_concurrent_consumers_do_not_double_deliver(
        self, gateway: QueueGateway
    ):
        await gateway.send({"x": 1})

        async def consume() -> list:
            return await gateway.receive(max_messages=5, wait_seconds=0.5)

        first, second = await asyncio.gather(consume(), consume())
        delivered = [m for m in first + second if m.body == {"x": 1}]
        assert len(delivered) == 1
