"""Process-local TaskStore for tests / single-process dev."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.modules.tasks.models import TaskStatus
from app.modules.tasks.store import TaskRecord


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

    async def mark_processing(self, task_id: str) -> None:
        await self._update_status(task_id, TaskStatus.PROCESSING)

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self._update_status(task_id, TaskStatus.COMPLETED, result=result)

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self._update_status(task_id, TaskStatus.FAILED, error=error)

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
