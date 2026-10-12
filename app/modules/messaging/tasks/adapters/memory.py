"""Process-local TaskStore for tests / single-process dev."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import (
    MAX_ATTEMPTS_EXCEEDED,
    TaskRecord,
    TaskRef,
)

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

    async def get(
        self, task_id: str, *, principal_id: str | None = None
    ) -> TaskRecord | None:
        task = self._tasks.get(task_id)
        if task is None or (
            principal_id is not None and task.principal_id != principal_id
        ):
            return None
        return task

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
        async with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                raise KeyError(task_id)
            if not _claimable(task, now):
                return False
            task.status = TaskStatus.PROCESSING
            task.attempts += 1
            task.locked_until = now + timedelta(seconds=lease_seconds)
            task.updated_at = now
            return True

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self._update_status(
            task_id, TaskStatus.COMPLETED, result=result, locked_until=None
        )

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self._update_status(
            task_id, TaskStatus.FAILED, error=error, locked_until=None
        )

    async def reclaim_stale_processing(
        self, *, now: datetime, limit: int = 100, max_attempts: int
    ) -> list[TaskRef]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        reclaimed: list[TaskRef] = []
        settled = 0
        async with self._lock:
            for task in self._tasks.values():
                if settled >= limit:
                    break
                if not _lease_expired(task, now):
                    continue
                settled += 1
                task.locked_until = None
                task.updated_at = now
                if task.attempts >= max_attempts:
                    task.status = TaskStatus.FAILED
                    task.error = MAX_ATTEMPTS_EXCEEDED
                else:
                    task.status = TaskStatus.QUEUED
                    reclaimed.append(
                        TaskRef(id=task.id, type=task.type, request_id=task.request_id)
                    )
        return reclaimed

    async def delete_expired(self, before: datetime, *, limit: int) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        async with self._lock:
            stale = [
                task_id
                for task_id, task in self._tasks.items()
                if task.expires_at <= before
            ][:limit]
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
            if result is not None:
                task.result = result
            if error is not None:
                task.error = error
            if locked_until is not _UNSET:
                task.locked_until = locked_until


def _lease_expired(task: TaskRecord, now: datetime) -> bool:
    return (
        task.status == TaskStatus.PROCESSING
        and task.locked_until is not None
        and task.locked_until <= now
    )


def _claimable(task: TaskRecord, now: datetime) -> bool:
    return task.status == TaskStatus.QUEUED or _lease_expired(task, now)
