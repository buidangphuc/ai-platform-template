"""RabbitMQ ``QueueGateway`` — optional. Install via ``[rabbitmq]`` extra."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.modules.messaging.queue.gateway import QueueMessage

try:
    import aio_pika
    from aio_pika.abc import AbstractIncomingMessage, AbstractRobustChannel
except ImportError:  # pragma: no cover - exercised only when extras missing
    aio_pika = None
    AbstractIncomingMessage = AbstractRobustChannel = None  # type: ignore[assignment,misc]


def _require_aio_pika() -> None:
    if aio_pika is None:
        raise RuntimeError(
            "RabbitMQ adapter requires the [rabbitmq] extra: "
            "uv pip install 'fastapi-template[rabbitmq]'"
        )


class RabbitMQQueueGateway:
    def __init__(self, *, url: str, queue_name: str) -> None:
        _require_aio_pika()
        if not url:
            raise ValueError("url is required for RabbitMQ gateway")
        self.url = url
        self.queue_name = queue_name
        self._connection = None
        self._channel: AbstractRobustChannel | None = None
        self._queue = None
        self._inflight: dict[str, AbstractIncomingMessage] = {}

    async def _ensure_ready(self) -> None:
        if self._channel is not None:
            return
        self._connection = await aio_pika.connect_robust(self.url)
        self._channel = await self._connection.channel()
        await self._channel.set_qos(prefetch_count=10)
        self._queue = await self._channel.declare_queue(self.queue_name, durable=True)

    async def send(self, payload: dict[str, Any]) -> str:
        await self._ensure_ready()
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._channel.default_exchange.publish(
            message, routing_key=self.queue_name
        )
        return message.message_id or ""

    async def receive(
        self,
        *,
        max_messages: int = 10,
        wait_seconds: float = 0.0,
    ) -> list[QueueMessage]:
        await self._ensure_ready()
        messages: list[QueueMessage] = []
        deadline = wait_seconds if wait_seconds > 0 else None

        async def _pull_one() -> AbstractIncomingMessage | None:
            return await self._queue.get(timeout=deadline, fail=False)

        first = await _pull_one()
        if first is None:
            return []
        messages.append(self._wrap(first))

        while len(messages) < max_messages:
            try:
                more = await asyncio.wait_for(_pull_one(), timeout=0.05)
            except TimeoutError:
                break
            if more is None:
                break
            messages.append(self._wrap(more))

        return messages

    async def ack(self, message: QueueMessage) -> None:
        incoming = self._inflight.pop(message.id, None)
        if incoming is not None:
            await incoming.ack()

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None:
        incoming = self._inflight.pop(message.id, None)
        if incoming is not None:
            await incoming.nack(requeue=requeue)

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None
            self._channel = None
            self._queue = None

    def _wrap(self, incoming: AbstractIncomingMessage) -> QueueMessage:
        message_id = incoming.message_id or str(incoming.delivery_tag)
        self._inflight[message_id] = incoming
        return QueueMessage(
            id=message_id,
            body=json.loads(incoming.body.decode("utf-8")),
            raw=incoming,
        )
