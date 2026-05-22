"""Redis Streams ``QueueGateway`` — uses XADD / XREADGROUP / XACK.

Suitable for production when the project already depends on Redis. Consumer
group is auto-created so the gateway is safe to start before producers.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.modules.queue.gateway import QueueMessage


class RedisStreamQueueGateway:
    def __init__(
        self,
        *,
        redis: Redis,
        stream: str,
        consumer_group: str = "workers",
        consumer_name: str | None = None,
    ) -> None:
        self.redis = redis
        self.stream = stream
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"worker-{uuid4().hex[:8]}"
        self._group_ready = False

    async def send(self, payload: dict[str, Any]) -> str:
        message_id = await self.redis.xadd(self.stream, {"body": json.dumps(payload)})
        return _decode(message_id)

    async def receive(
        self,
        *,
        max_messages: int = 10,
        wait_seconds: float = 0.0,
    ) -> list[QueueMessage]:
        await self._ensure_group()

        block_ms = int(wait_seconds * 1000) if wait_seconds > 0 else 0
        response = await self.redis.xreadgroup(
            groupname=self.consumer_group,
            consumername=self.consumer_name,
            streams={self.stream: ">"},
            count=max_messages,
            block=block_ms,
        )
        if not response:
            return []

        messages: list[QueueMessage] = []
        for _stream_name, entries in response:
            for raw_id, fields in entries:
                message_id = _decode(raw_id)
                body_raw = fields.get("body") or fields.get(b"body")
                body = json.loads(_decode(body_raw)) if body_raw else {}
                messages.append(QueueMessage(id=message_id, body=body, raw=fields))
        return messages

    async def ack(self, message: QueueMessage) -> None:
        await self.redis.xack(self.stream, self.consumer_group, message.id)

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None:
        await self.redis.xack(self.stream, self.consumer_group, message.id)
        if requeue:
            body = dict(message.body)
            body.setdefault("original_message_id", message.id)
            await self.redis.xadd(
                self.stream,
                {"body": json.dumps(body)},
            )

    async def close(self) -> None:
        return None

    async def _ensure_group(self) -> None:
        if self._group_ready:
            return
        try:
            await self.redis.xgroup_create(
                self.stream, self.consumer_group, id="0", mkstream=True
            )
        except ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise
        self._group_ready = True


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
