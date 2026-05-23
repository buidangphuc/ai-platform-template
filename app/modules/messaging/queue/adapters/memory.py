"""In-memory queue adapter — process-local, used for tests and local dev."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

from app.modules.messaging.queue.gateway import QueueMessage


class InMemoryQueueGateway:
    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._queue: asyncio.Queue[QueueMessage] = asyncio.Queue()
        self._inflight: dict[str, QueueMessage] = {}
        self._dead_letter: list[QueueMessage] = []
        self._closed = False

    async def send(self, payload: dict[str, Any]) -> str:
        if self._closed:
            raise RuntimeError("queue is closed")
        message = QueueMessage(id=str(uuid4()), body=payload)
        await self._queue.put(message)
        return message.id

    async def receive(
        self,
        *,
        max_messages: int = 10,
        wait_seconds: float = 0.0,
    ) -> list[QueueMessage]:
        if self._closed:
            return []
        messages: list[QueueMessage] = []
        deadline_wait = max(wait_seconds, 0.0)

        try:
            first = await asyncio.wait_for(
                self._queue.get(), timeout=deadline_wait or None
            )
        except TimeoutError:
            return []

        messages.append(first)

        while len(messages) < max_messages:
            try:
                messages.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break

        for msg in messages:
            self._inflight[msg.id] = msg
        return messages

    async def ack(self, message: QueueMessage) -> None:
        self._inflight.pop(message.id, None)

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None:
        stored = self._inflight.pop(message.id, None)
        if stored is None:
            return
        if requeue:
            requeued = QueueMessage(
                id=stored.id,
                body=stored.body,
                receive_count=stored.receive_count + 1,
            )
            await self._queue.put(requeued)
        else:
            self._dead_letter.append(stored)

    async def close(self) -> None:
        self._closed = True

    def pending_count(self) -> int:
        return self._queue.qsize()

    def inflight_count(self) -> int:
        return len(self._inflight)

    def dead_letter_count(self) -> int:
        return len(self._dead_letter)

    def dead_letter_messages(self) -> list[QueueMessage]:
        return list(self._dead_letter)
