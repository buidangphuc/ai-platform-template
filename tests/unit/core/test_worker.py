import asyncio

import pytest

from app.core.worker import AsyncPollingWorker
from app.modules.queue.adapters.memory import InMemoryQueueGateway
from app.modules.queue.gateway import QueueMessage


class _RecordingGateway:
    def __init__(self) -> None:
        self.acked: list[QueueMessage] = []
        self.nacked: list[tuple[QueueMessage, bool]] = []

    async def send(self, payload: dict) -> str:
        return "unused"

    async def receive(
        self,
        *,
        max_messages: int = 10,
        wait_seconds: float = 0.0,
    ) -> list[QueueMessage]:
        return []

    async def ack(self, message: QueueMessage) -> None:
        self.acked.append(message)

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None:
        self.nacked.append((message, requeue))

    async def close(self) -> None:
        return None


async def test_worker_processes_messages_and_acks_them():
    gateway = InMemoryQueueGateway()
    await gateway.send({"value": 1})
    await gateway.send({"value": 2})

    seen: list[dict] = []

    async def handler(message):
        seen.append(message.body)

    worker = AsyncPollingWorker(
        gateway=gateway,
        handler=handler,
        max_concurrent=2,
        poll_interval_seconds=0.01,
        receive_wait_seconds=0.1,
    )

    async def stop_when_done() -> None:
        for _ in range(50):
            if len(seen) >= 2:
                break
            await asyncio.sleep(0.05)
        worker.request_shutdown()

    stopper = asyncio.create_task(stop_when_done())
    await worker.run()
    await stopper

    assert sorted(m["value"] for m in seen) == [1, 2]
    assert gateway.inflight_count() == 0


async def test_worker_nacks_message_on_handler_exception():
    gateway = InMemoryQueueGateway()
    await gateway.send({"value": 1})

    call_count = 0

    async def handler(message):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("boom")

    worker = AsyncPollingWorker(
        gateway=gateway,
        handler=handler,
        max_concurrent=1,
        poll_interval_seconds=0.01,
        receive_wait_seconds=0.05,
    )

    async def stop_when_done() -> None:
        for _ in range(50):
            if call_count >= 2:
                break
            await asyncio.sleep(0.05)
        worker.request_shutdown()

    stopper = asyncio.create_task(stop_when_done())
    await worker.run()
    await stopper

    assert call_count >= 2  # original + at least one requeue


async def test_worker_requeues_failed_message_before_max_attempts():
    gateway = _RecordingGateway()

    async def fail(_message):
        raise RuntimeError("boom")

    worker = AsyncPollingWorker(
        gateway=gateway,
        handler=fail,
        max_attempts=3,
    )

    message = QueueMessage(id="msg-1", body={"value": 1}, receive_count=2)
    await worker._dispatch(message)

    assert gateway.acked == []
    assert gateway.nacked == [(message, True)]


async def test_worker_drops_failed_message_at_max_attempts():
    gateway = _RecordingGateway()

    async def fail(_message):
        raise RuntimeError("boom")

    worker = AsyncPollingWorker(
        gateway=gateway,
        handler=fail,
        max_attempts=3,
    )

    message = QueueMessage(id="msg-1", body={"value": 1}, receive_count=3)
    await worker._dispatch(message)

    assert gateway.acked == []
    assert gateway.nacked == [(message, False)]


async def test_worker_rejects_invalid_concurrency():
    gateway = InMemoryQueueGateway()

    async def noop(_):
        pass

    with pytest.raises(ValueError):
        AsyncPollingWorker(gateway=gateway, handler=noop, max_concurrent=0)

    with pytest.raises(ValueError):
        AsyncPollingWorker(gateway=gateway, handler=noop, poll_interval_seconds=-1)

    with pytest.raises(ValueError):
        AsyncPollingWorker(gateway=gateway, handler=noop, max_attempts=0)
