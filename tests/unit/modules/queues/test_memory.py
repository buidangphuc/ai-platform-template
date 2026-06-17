import pytest

from app.modules.messaging.queue.adapters.memory import InMemoryQueueGateway
from app.modules.messaging.queue.gateway import QueueGateway

from .conformance import QueueGatewayConformance


class TestInMemoryQueueGateway(QueueGatewayConformance):
    @pytest.fixture
    def gateway_factory(self):
        async def _build() -> QueueGateway:
            return InMemoryQueueGateway(name="test")

        return _build


async def test_in_memory_gateway_rejects_send_after_close():
    gateway = InMemoryQueueGateway()
    await gateway.close()

    with pytest.raises(RuntimeError):
        await gateway.send({})


async def test_in_memory_gateway_exposes_pending_and_inflight_counts():
    gateway = InMemoryQueueGateway()
    await gateway.send({"a": 1})
    await gateway.send({"b": 2})

    assert gateway.pending_count() == 2
    assert gateway.inflight_count() == 0

    messages = await gateway.receive(max_messages=2, wait_seconds=0.1)
    assert gateway.pending_count() == 0
    assert gateway.inflight_count() == 2

    for msg in messages:
        await gateway.ack(msg)
    assert gateway.inflight_count() == 0


async def test_in_memory_gateway_routes_unrequeued_nack_to_dead_letter():
    gateway = InMemoryQueueGateway()
    await gateway.send({"event": "1"})

    [message] = await gateway.receive(max_messages=1, wait_seconds=0.1)
    await gateway.nack(message, requeue=False)

    assert gateway.dead_letter_count() == 1
    assert gateway.dead_letter_messages()[0].body == {"event": "1"}
    assert gateway.pending_count() == 0


async def test_in_memory_gateway_requeue_increments_receive_count():
    gateway = InMemoryQueueGateway()
    await gateway.send({"event": "1"})

    [first] = await gateway.receive(max_messages=1, wait_seconds=0.1)
    await gateway.nack(first, requeue=True)

    [second] = await gateway.receive(max_messages=1, wait_seconds=0.1)

    assert first.receive_count == 1
    assert second.receive_count == 2
    assert gateway.dead_letter_count() == 0
