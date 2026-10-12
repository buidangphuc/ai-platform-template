"""Redis-backed ``TaskStore`` — JSON values keyed by ``{prefix}:{task_id}``.

Trades durability for very low latency reads. TTL falls out of ``expires_at``
on insert so cleanup is free; ``delete_expired`` is a no-op.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from redis.exceptions import WatchError

from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import TaskRecord, TaskRef


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

    async def mark_processing(
        self,
        task_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = now or datetime.now(UTC)

        def claim(task: TaskRecord) -> bool:
            if task.status != TaskStatus.QUEUED and not _lease_expired(task, now):
                return False
            task.status = TaskStatus.PROCESSING
            task.attempts += 1
            task.locked_until = now + timedelta(seconds=lease_seconds)
            task.updated_at = now
            return True

        task, applied = await self._transition(self._key(task_id), claim)
        if task is None:
            raise KeyError(task_id)
        return applied

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self._update(
            task_id, status=TaskStatus.COMPLETED, result=result, locked_until=None
        )

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self._update(
            task_id, status=TaskStatus.FAILED, error=error, locked_until=None
        )

    async def reclaim_stale_processing(
        self, *, now: datetime, limit: int = 100
    ) -> list[TaskRef]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        reclaimed: list[TaskRef] = []

        def reclaim(task: TaskRecord) -> bool:
            if not _lease_expired(task, now):
                return False
            task.status = TaskStatus.QUEUED
            task.locked_until = None
            task.updated_at = now
            return True

        # Best-effort scan; Redis-backed task store is meant for low-volume
        # template demo so SCAN is acceptable. Production volumes should swap
        # to Postgres.
        cursor = 0
        while len(reclaimed) < limit:
            cursor, keys = await self.redis.scan(
                cursor=cursor, match=f"{self.prefix}:*", count=200
            )
            for raw_key in keys:
                if len(reclaimed) >= limit:
                    break
                key = _decode(raw_key)
                task, applied = await self._transition(key, reclaim)
                if task is not None and applied:
                    reclaimed.append(TaskRef(id=task.id, type=task.type))
            if cursor == 0:
                break
        return reclaimed

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
        locked_until: datetime | None = None,
    ) -> None:
        key = self._key(task_id)
        raw = await self.redis.get(key)
        if raw is None:
            raise KeyError(task_id)

        task = _deserialize(_decode(raw))
        task.status = status
        task.updated_at = datetime.now(UTC)
        task.locked_until = locked_until
        if result is not None:
            task.result = result
        if error is not None:
            task.error = error

        remaining = await self.redis.ttl(key)
        ttl = remaining if remaining and remaining > 0 else 1
        await self.redis.setex(key, ttl, _serialize(task))

    async def _transition(
        self,
        key: str,
        mutate: Callable[[TaskRecord], bool],
    ) -> tuple[TaskRecord | None, bool]:
        """Atomic read-modify-write (WATCH/MULTI): ``mutate`` returns whether to save.

        Returns ``(None, False)`` when the key is gone.
        """
        async with self.redis.pipeline(transaction=True) as pipe:
            while True:
                try:
                    await pipe.watch(key)
                    raw = await pipe.get(key)
                    if raw is None:
                        await pipe.unwatch()
                        return None, False
                    task = _deserialize(_decode(raw))
                    if not mutate(task):
                        await pipe.unwatch()
                        return task, False
                    remaining = await pipe.ttl(key)
                    ttl = remaining if remaining and remaining > 0 else 1
                    pipe.multi()
                    pipe.setex(key, ttl, _serialize(task))
                    await pipe.execute()
                    return task, True
                except WatchError:
                    continue

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
        expires_at=_parse_required_dt(data["expires_at"]),
        created_at=_parse_dt(data.get("created_at")),
        updated_at=_parse_dt(data.get("updated_at")),
    )


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _parse_required_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _lease_expired(task: TaskRecord, now: datetime) -> bool:
    return (
        task.status == TaskStatus.PROCESSING
        and task.locked_until is not None
        and task.locked_until <= now
    )
