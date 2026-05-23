"""Task submit / poll / transition service, decoupled from dispatch backend.

A ``TaskDispatcher`` decides *how* a newly created task is announced for the
worker:

- ``QueueTaskDispatcher`` — fire-and-forget directly to the queue. Simple but
  not atomic with the DB write; on queue-send failure the task record is
  orphaned (worker never picks it up).
- ``OutboxTaskDispatcher`` — enqueue into ``messaging/outbox/`` in the same
  transaction as task creation, then a separate publisher process pushes to
  the queue. Atomic + retryable, at the cost of an extra hop.

Pick via ``Settings.TASKS_DISPATCH_BACKEND`` (``"queue"`` or ``"outbox"``).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable
from uuid import uuid4

from app.core.errors import NotFoundError
from app.modules.messaging.outbox.store import OutboxStore
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import TaskRecord, TaskStore


@runtime_checkable
class TaskDispatcher(Protocol):
    async def dispatch(self, task_id: str, *, type: str) -> None: ...


class QueueTaskDispatcher:
    """Direct ``queue.send`` — simple but non-atomic with task creation."""

    def __init__(self, queue: QueueGateway) -> None:
        self.queue = queue

    async def dispatch(self, task_id: str, *, type: str) -> None:
        await self.queue.send({"task_id": task_id, "type": type})


class OutboxTaskDispatcher:
    """Enqueue an outbox event so dispatch and task-create share a DB transaction."""

    def __init__(
        self,
        outbox: OutboxStore,
        *,
        event_type_prefix: str = "task",
    ) -> None:
        self.outbox = outbox
        self.event_type_prefix = event_type_prefix

    async def dispatch(self, task_id: str, *, type: str) -> None:
        await self.outbox.enqueue(
            event_type=f"{self.event_type_prefix}.{type}",
            payload={"task_id": task_id, "type": type},
        )


class TaskService:
    def __init__(
        self,
        *,
        store: TaskStore,
        dispatcher: TaskDispatcher,
        ttl_seconds: int = 86_400,
        lease_seconds: int = 300,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        self.store = store
        self.dispatcher = dispatcher
        self.ttl_seconds = ttl_seconds
        self.lease_seconds = lease_seconds

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
        await self.dispatcher.dispatch(task.id, type=type)
        return task

    async def require(self, task_id: str) -> TaskRecord:
        record = await self.store.get(task_id)
        if record is None:
            raise NotFoundError(f"Task {task_id} not found", code="task_not_found")
        return record

    async def mark_processing(self, task_id: str) -> None:
        await self.store.mark_processing(task_id, lease_seconds=self.lease_seconds)

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self.store.mark_completed(task_id, result)

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self.store.mark_failed(task_id, error)

    async def reclaim_stale_processing(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
    ) -> int:
        return await self.store.reclaim_stale_processing(
            now=now or datetime.now(UTC), limit=limit
        )
