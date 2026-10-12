"""Task submit / poll / transition service, decoupled from dispatch backend.

A ``TaskDispatcher`` owns *both* halves of submission, because atomicity between
them is the dispatcher's property, not the service's:

- ``QueueTaskDispatcher`` — create the task, then ``queue.send`` directly. Works
  with any task store but is **not atomic**: if the send fails the task row is
  orphaned (it stays QUEUED and no worker ever sees it).
- ``PostgresTaskOutboxDispatcher`` (``tasks/outbox.py``) — inserts the task row
  and its outbox event in **one** Postgres transaction; an outbox relay (run by
  the worker process) then publishes the event to the queue. Atomic and
  retryable, at the cost of an extra hop. Only valid with
  ``TASK_STORE_BACKEND=postgres`` (settings enforce it).

Pick via ``Settings.TASKS_DISPATCH_BACKEND`` (``"queue"`` or ``"outbox"``). Both
announce a task with the same ``TaskMessage`` contract.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import uuid4

from app.core.errors import NotFoundError
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.message import TaskMessage
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import TaskRecord, TaskStore


class TaskDispatcher(Protocol):
    async def submit(self, task: TaskRecord) -> None:
        """Persist a new QUEUED task and announce it to the worker."""
        ...

    async def reclaim(self, *, now: datetime, limit: int, max_attempts: int) -> int:
        """Settle expired-lease PROCESSING tasks (see ``TaskStore``); announce requeued.

        Returns how many were requeued.
        """
        ...


class QueueTaskDispatcher:
    """Create, then direct ``queue.send`` — simple but non-atomic."""

    def __init__(self, store: TaskStore, queue: QueueGateway) -> None:
        self.store = store
        self.queue = queue

    async def submit(self, task: TaskRecord) -> None:
        await self.store.create(task)
        await self._announce(task.id, task.type)

    async def reclaim(self, *, now: datetime, limit: int, max_attempts: int) -> int:
        reclaimed = await self.store.reclaim_stale_processing(
            now=now, limit=limit, max_attempts=max_attempts
        )
        for ref in reclaimed:
            await self._announce(ref.id, ref.type)
        return len(reclaimed)

    async def _announce(self, task_id: str, type: str) -> None:
        await self.queue.send(TaskMessage(task_id=task_id, type=type).to_body())


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
        await self.dispatcher.submit(task)
        return task

    async def require(self, task_id: str) -> TaskRecord:
        record = await self.store.get(task_id)
        if record is None:
            raise NotFoundError(f"Task {task_id} not found", code="task_not_found")
        return record

    async def mark_processing(self, task_id: str) -> bool:
        """Claim the task for this worker; ``False`` means skip it (see the store)."""
        return await self.store.mark_processing(
            task_id, lease_seconds=self.lease_seconds
        )

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self.store.mark_completed(task_id, result)

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self.store.mark_failed(task_id, error)

    async def reclaim_stale_processing(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        max_attempts: int,
    ) -> int:
        return await self.dispatcher.reclaim(
            now=now or datetime.now(UTC), limit=limit, max_attempts=max_attempts
        )
