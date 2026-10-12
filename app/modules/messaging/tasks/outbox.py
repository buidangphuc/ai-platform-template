"""Transactional-outbox dispatch for tasks (Postgres task store only).

``PostgresTaskOutboxDispatcher`` writes the task row and its outbox event in one
transaction, so a task exists if and only if its announcement will be published.
``TaskQueueOutboxSink`` is the relay side: it turns that event into the flat
``TaskMessage`` body the worker parses.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.messaging.outbox.adapters import new_outbox_row
from app.modules.messaging.outbox.store import OutboxRecord
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.adapters.postgres import (
    new_task_row,
    reclaim_stale_in,
)
from app.modules.messaging.tasks.message import TaskMessage
from app.modules.messaging.tasks.store import TaskRecord

TASK_EVENT_PREFIX = "task."


def _task_event(session: AsyncSession, *, task_id: str, type: str) -> None:
    message = TaskMessage(task_id=task_id, type=type)
    session.add(
        new_outbox_row(
            event_type=f"{TASK_EVENT_PREFIX}{type}", payload=message.to_body()
        )
    )


class PostgresTaskOutboxDispatcher:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def submit(self, task: TaskRecord) -> None:
        async with self.sessionmaker() as session, session.begin():
            session.add(new_task_row(task))
            _task_event(session, task_id=task.id, type=task.type)

    async def reclaim(self, *, now: datetime, limit: int) -> int:
        async with self.sessionmaker() as session, session.begin():
            reclaimed = await reclaim_stale_in(session, now=now, limit=limit)
            for ref in reclaimed:
                _task_event(session, task_id=ref.id, type=ref.type)
            return len(reclaimed)


class TaskQueueOutboxSink:
    """Relay sink: publish a ``task.*`` outbox event as a flat ``TaskMessage``."""

    def __init__(self, queue: QueueGateway) -> None:
        self.queue = queue

    async def publish(self, record: OutboxRecord, *, now: datetime) -> None:
        message = TaskMessage.from_body(record.payload)
        await self.queue.send(message.to_body())
