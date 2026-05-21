"""Submit / poll / mark Task transitions, decoupled from any persistence backend.

The service owns the queue + store wiring: ``submit`` writes a record and
enqueues a notification; the worker calls ``mark_*`` on success/failure.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from app.core.errors import NotFoundError
from app.modules.queue.gateway import QueueGateway
from app.modules.tasks.models import TaskStatus
from app.modules.tasks.store import TaskRecord, TaskStore


class TaskService:
    def __init__(
        self,
        *,
        store: TaskStore,
        queue: QueueGateway,
        ttl_seconds: int = 86_400,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        self.store = store
        self.queue = queue
        self.ttl_seconds = ttl_seconds

    async def submit(
        self,
        *,
        type: str,
        payload: dict[str, Any],
    ) -> TaskRecord:
        now = datetime.now(UTC)
        task = TaskRecord(
            id=str(uuid4()),
            type=type,
            status=TaskStatus.QUEUED,
            payload=payload,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            created_at=now,
            updated_at=now,
        )
        await self.store.create(task)
        await self.queue.send({"task_id": task.id, "type": type})
        return task

    async def require(self, task_id: str) -> TaskRecord:
        record = await self.store.get(task_id)
        if record is None:
            raise NotFoundError(f"Task {task_id} not found", code="task_not_found")
        return record

    async def mark_processing(self, task_id: str) -> None:
        await self.store.mark_processing(task_id)

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self.store.mark_completed(task_id, result)

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self.store.mark_failed(task_id, error)
