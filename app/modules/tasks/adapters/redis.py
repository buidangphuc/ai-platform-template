"""Redis-backed ``TaskStore`` — JSON values keyed by ``{prefix}:{task_id}``.

Trades durability for very low latency reads. TTL falls out of ``expires_at``
on insert so cleanup is free; ``delete_expired`` is a no-op.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.modules.tasks.models import TaskStatus
from app.modules.tasks.store import TaskRecord


class RedisTaskStore:
    def __init__(self, *, redis: Redis, prefix: str = "tasks") -> None:
        self.redis = redis
        self.prefix = prefix

    async def create(self, task: TaskRecord) -> None:
        now = datetime.now(UTC)
        task.created_at = task.created_at or now
        task.updated_at = now
        ttl = max(int((task.expires_at - now).total_seconds()), 1)
        await self.redis.setex(self._key(task.id), ttl, _serialize(task))

    async def get(self, task_id: str) -> TaskRecord | None:
        raw = await self.redis.get(self._key(task_id))
        if raw is None:
            return None
        return _deserialize(_decode(raw))

    async def mark_processing(self, task_id: str) -> None:
        await self._update(task_id, status=TaskStatus.PROCESSING, bump_attempts=True)

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self._update(task_id, status=TaskStatus.COMPLETED, result=result)

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self._update(task_id, status=TaskStatus.FAILED, error=error)

    async def delete_expired(self, before: datetime) -> int:
        return 0  # Redis TTL handles expiry automatically

    async def close(self) -> None:
        return None

    async def _update(
        self,
        task_id: str,
        *,
        status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        bump_attempts: bool = False,
    ) -> None:
        key = self._key(task_id)
        raw = await self.redis.get(key)
        if raw is None:
            raise KeyError(task_id)

        task = _deserialize(_decode(raw))
        task.status = status
        task.updated_at = datetime.now(UTC)
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error
        if bump_attempts:
            task.attempts += 1

        remaining = await self.redis.ttl(key)
        ttl = remaining if remaining and remaining > 0 else 1
        await self.redis.setex(key, ttl, _serialize(task))

    def _key(self, task_id: str) -> str:
        return f"{self.prefix}:{task_id}"


def _serialize(task: TaskRecord) -> str:
    payload = {
        "id": task.id,
        "type": task.type,
        "status": str(task.status),
        "payload": task.payload,
        "result": task.result,
        "error": task.error,
        "attempts": task.attempts,
        "locked_until": task.locked_until.isoformat() if task.locked_until else None,
        "expires_at": task.expires_at.isoformat(),
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }
    return json.dumps(payload)


def _deserialize(raw: str) -> TaskRecord:
    data = json.loads(raw)
    return TaskRecord(
        id=data["id"],
        type=data["type"],
        status=TaskStatus(data["status"]),
        payload=data["payload"],
        result=data.get("result"),
        error=data.get("error"),
        attempts=data.get("attempts", 0),
        locked_until=_parse_dt(data.get("locked_until")),
        expires_at=_parse_dt(data["expires_at"]),
        created_at=_parse_dt(data.get("created_at")),
        updated_at=_parse_dt(data.get("updated_at")),
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)
