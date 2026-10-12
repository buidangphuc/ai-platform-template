"""Redis Streams ``QueueGateway`` — XADD / XREADGROUP / XAUTOCLAIM / XACK.

Suitable for production when the project already depends on Redis (>= 6.2 for
XAUTOCLAIM). Consumer group is auto-created so the gateway is safe to start
before producers.

Redelivery model: an entry stays in the group's pending list until it is acked
or dead-lettered. ``receive`` first reclaims entries idle longer than
``min_idle_seconds`` (a crashed consumer's work, or a nacked entry) and maps
the stream's own delivery counter to ``QueueMessage.receive_count``. Entries
delivered more than ``max_deliveries`` times move to ``<stream>:dead``.
"""

from __future__ import annotations

import json
import os
from typing import Any
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import ResponseError

from app.modules.messaging.queue.gateway import QueueMessage


class RedisStreamQueueGateway:
    def __init__(
        self,
        *,
        redis: Redis,
        stream: str,
        consumer_group: str = "workers",
        consumer_name: str | None = None,
        min_idle_seconds: float = 60.0,
        max_deliveries: int = 5,
    ) -> None:
        self.redis = redis
        self.stream = stream
        self.dead_stream = f"{stream}:dead"
        self.consumer_group = consumer_group
        # Stable across restarts so a restarted pod resumes its own pending
        # entries; HOSTNAME is the pod name on Kubernetes.
        self.consumer_name = (
            consumer_name or os.environ.get("HOSTNAME") or f"worker-{uuid4().hex[:8]}"
        )
        self.min_idle_ms = int(min_idle_seconds * 1000)
        self.max_deliveries = max_deliveries
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

        messages = await self._claim_idle(max_messages)

        remaining = max_messages - len(messages)
        if remaining > 0:
            # Only block when nothing was reclaimed; redis treats BLOCK 0 as
            # "forever", so omit it for a non-blocking read.
            block_ms = int(wait_seconds * 1000) if wait_seconds > 0 else None
            if messages:
                block_ms = None
            response = await self.redis.xreadgroup(
                groupname=self.consumer_group,
                consumername=self.consumer_name,
                streams={self.stream: ">"},
                count=remaining,
                block=block_ms,
            )
            for _stream_name, entries in response or []:
                for raw_id, fields in entries:
                    messages.append(_to_message(raw_id, fields, receive_count=1))
        return messages

    async def ack(self, message: QueueMessage) -> None:
        await self.redis.xack(self.stream, self.consumer_group, message.id)

    async def nack(self, message: QueueMessage, *, requeue: bool = True) -> None:
        if not requeue:
            await self._dead_letter(message.id, message.body, reason="rejected")
            return
        # Keep the entry pending (same id, same delivery counter) and mark it
        # as idle for ``min_idle`` so the next receive reclaims it. Single
        # command, so there is no ack-then-add window to lose the message in.
        await self.redis.xclaim(
            self.stream,
            self.consumer_group,
            self.consumer_name,
            min_idle_time=0,
            message_ids=[message.id],
            idle=self.min_idle_ms,
            justid=True,
        )

    async def close(self) -> None:
        return None

    async def _claim_idle(self, count: int) -> list[QueueMessage]:
        _next, entries, _deleted = await self.redis.xautoclaim(
            self.stream,
            self.consumer_group,
            self.consumer_name,
            min_idle_time=self.min_idle_ms,
            start_id="0-0",
            count=count,
        )
        messages: list[QueueMessage] = []
        for raw_id, fields in entries:
            message_id = _decode(raw_id)
            if not fields:  # entry trimmed from the stream; drop the dangling PEL ref
                await self.redis.xack(self.stream, self.consumer_group, message_id)
                continue
            pending = await self.redis.xpending_range(
                self.stream,
                self.consumer_group,
                min=message_id,
                max=message_id,
                count=1,
            )
            delivered = int(pending[0]["times_delivered"]) if pending else 1
            message = _to_message(raw_id, fields, receive_count=delivered)
            if delivered > self.max_deliveries:
                await self._dead_letter(
                    message.id, message.body, reason="max_deliveries", count=delivered
                )
                continue
            messages.append(message)
        return messages

    async def _dead_letter(
        self,
        message_id: str,
        body: dict[str, Any],
        *,
        reason: str,
        count: int | None = None,
    ) -> None:
        fields = {
            "body": json.dumps(body),
            "original_message_id": message_id,
            "reason": reason,
        }
        if count is not None:
            fields["receive_count"] = str(count)
        # MULTI/EXEC: the entry is never acked without also landing in the DLQ.
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.xadd(self.dead_stream, fields)
            pipe.xack(self.stream, self.consumer_group, message_id)
            await pipe.execute()

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


def _to_message(
    raw_id: Any, fields: dict[Any, Any], *, receive_count: int
) -> QueueMessage:
    body_raw = fields.get("body") or fields.get(b"body")
    return QueueMessage(
        id=_decode(raw_id),
        body=json.loads(_decode(body_raw)) if body_raw else {},
        receive_count=receive_count,
        raw=fields,
    )


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
