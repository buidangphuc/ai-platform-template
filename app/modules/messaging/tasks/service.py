"""Task submit / poll / transition service.

Delivery is "store the row, then send" on every task store, and the reclaim
sweep repairs whatever the send lost:

- ``submit`` creates the task and sends one ``TaskMessage``; a failed send is
  logged and the task stays QUEUED.
- ``reclaim_stale_processing`` requeues PROCESSING tasks whose lease expired and
  announces them, then announces QUEUED tasks nobody picked up for
  ``queued_reannounce_seconds``. A task is announced at most once per interval.

Delivery is at-least-once: a task can be announced more than once, and the
claim in ``mark_processing`` makes the duplicates harmless.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from loguru import logger

from app.core.errors import NotFoundError
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.message import TaskMessage
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import TaskRecord, TaskRef, TaskStore


class TaskService:
    def __init__(
        self,
        *,
        store: TaskStore,
        queue: QueueGateway,
        ttl_seconds: int = 86_400,
        lease_seconds: int = 300,
        queued_reannounce_seconds: int = 60,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        if queued_reannounce_seconds <= 0:
            raise ValueError("queued_reannounce_seconds must be positive")
        self.store = store
        self.queue = queue
        self.ttl_seconds = ttl_seconds
        self.lease_seconds = lease_seconds
        self.queued_reannounce_seconds = queued_reannounce_seconds

    async def submit(
        self,
        *,
        type: str,
        payload: dict[str, Any],
        principal_id: str,
        request_id: str | None = None,
    ) -> TaskRecord:
        now = datetime.now(UTC)
        task = TaskRecord(
            id=str(uuid4()),
            type=type,
            principal_id=principal_id,
            request_id=request_id,
            status=TaskStatus.QUEUED,
            payload=payload,
            expires_at=now + timedelta(seconds=self.ttl_seconds),
            created_at=now,
            updated_at=now,
        )
        await self.store.create(task)
        await self._announce(TaskRef(task.id, task.type, task.request_id))
        return task

    async def require(self, task_id: str) -> TaskRecord:
        """Owner-agnostic read, for the worker. API reads use ``require_owned``."""
        record = await self.store.get(task_id)
        if record is None:
            raise NotFoundError(f"Task {task_id} not found", code="task_not_found")
        return record

    async def require_owned(
        self, task_id: str, *, principal_id: str, type: str
    ) -> TaskRecord:
        """The task if ``principal_id`` submitted it and it is a ``type`` task; else 404."""
        record = await self.store.get(task_id, principal_id=principal_id)
        if record is None or record.type != type:
            raise NotFoundError(f"Task {task_id} not found", code="task_not_found")
        return record

    async def mark_processing(self, task_id: str) -> bool:
        """Claim the task for this worker; ``False`` means skip it (see the store)."""
        return await self.store.mark_processing(
            task_id, lease_seconds=self.lease_seconds
        )

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> bool:
        return await self.store.mark_completed(task_id, result)

    async def mark_failed(self, task_id: str, error: str) -> bool:
        return await self.store.mark_failed(task_id, error)

    async def reclaim_stale_processing(
        self,
        *,
        now: datetime | None = None,
        limit: int = 100,
        max_attempts: int,
    ) -> int:
        """Requeue expired-lease tasks and re-announce stale QUEUED ones.

        Each of the two steps takes up to ``limit`` tasks. A failed send is
        logged and does not stop the others; the task is announced again once
        ``queued_reannounce_seconds`` have passed. Returns how many tasks were
        announced or attempted.
        """
        now = now or datetime.now(UTC)
        requeued = await self.store.reclaim_stale_processing(
            now=now, limit=limit, max_attempts=max_attempts
        )
        stale = await self.store.list_stale_queued(
            now=now, older_than_seconds=self.queued_reannounce_seconds, limit=limit
        )
        for ref in (*requeued, *stale):
            await self._announce(ref)
        return len(requeued) + len(stale)

    async def _announce(self, ref: TaskRef) -> None:
        message = TaskMessage(task_id=ref.id, type=ref.type, request_id=ref.request_id)
        try:
            await self.queue.send(message.to_body())
        except Exception:
            logger.exception("tasks.announce_failed task_id={}", ref.id)
