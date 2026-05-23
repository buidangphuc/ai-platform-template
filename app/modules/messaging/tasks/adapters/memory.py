"""Process-local TaskStore for tests / single-process dev."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import TaskRecord

_UNSET: Any = object()


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, TaskRecord] = {}
        self._lock = asyncio.Lock()

    async def create(self, task: TaskRecord) -> None:
        async with self._lock:
            if task.id in self._tasks:
                raise ValueError(f"task {task.id} already exists")
            now = datetime.now(UTC)
            task.created_at = task.created_at or now
            task.updated_at = now
            self._tasks[task.id] = task

    async def get(self, task_id: str) -> TaskRecord | None:
        return self._tasks.get(task_id)

    async def mark_processing(self, task_id: str, *, lease_seconds: int) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        await self._update_status(
            task_id,
            TaskStatus.PROCESSING,
            locked_until=datetime.now(UTC) + timedelta(seconds=lease_seconds),
        )

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self._update_status(
            task_id, TaskStatus.COMPLETED, result=result, locked_until=None
        )

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self._update_status(
            task_id, TaskStatus.FAILED, error=error, locked_until=None
        )

    async def reclaim_stale_processing(self, *, now: datetime, limit: int = 100) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        reclaimed = 0
        async with self._lock:
            for task in self._tasks.values():
                if reclaimed >= limit:
                    break
                if (
                    task.status == TaskStatus.PROCESSING
                    and task.locked_until is not None
                    and task.locked_until <= now
                ):
                    task.status = TaskStatus.QUEUED
                    task.locked_until = None
                    task.updated_at = now
                    reclaimed += 1
        return reclaimed

    async def delete_expired(self, before: datetime) -> int:
        async with self._lock:
            stale = [
                task_id
                for task_id, task in self._tasks.items()
                if task.expires_at <= before
            ]
            for task_id in stale:
                self._tasks.pop(task_id, None)
            return len(stale)

    async def close(self) -> None:
        return None

    async def _update_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        locked_until: Any = _UNSET,
    ) -> None:
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            task.status = status
            task.updated_at = datetime.now(UTC)
            if status == TaskStatus.PROCESSING:
                task.attempts += 1
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error
            if locked_until is not _UNSET:
                task.locked_until = locked_until
