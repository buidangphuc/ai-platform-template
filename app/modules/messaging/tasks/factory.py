"""Select a ``TaskStore`` + ``TaskDispatcher`` based on Settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.messaging.outbox.store import OutboxStore
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.service import (
    OutboxTaskDispatcher,
    QueueTaskDispatcher,
    TaskDispatcher,
)
from app.modules.messaging.tasks.store import TaskStore

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_task_store(
    settings: Settings,
    *,
    sessionmaker: async_sessionmaker[AsyncSession] | None = None,
    redis: Redis | None = None,
) -> TaskStore:
    backend = settings.TASK_STORE_BACKEND

    if backend == "memory":
        from app.modules.messaging.tasks.adapters.memory import InMemoryTaskStore

        return InMemoryTaskStore()

    if backend == "postgres":
        if sessionmaker is None:
            raise RuntimeError("sessionmaker required for postgres task store")
        from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore

        return PostgresTaskStore(sessionmaker)

    if backend == "redis":
        if redis is None:
            raise RuntimeError("redis client required for redis task store")
        from app.modules.messaging.tasks.adapters.redis import RedisTaskStore

        return RedisTaskStore(redis=redis, prefix=settings.TASK_REDIS_PREFIX)

    raise ValueError(f"Unknown TASK_STORE_BACKEND={backend!r}")


def build_task_dispatcher(
    settings: Settings,
    *,
    queue: QueueGateway | None = None,
    outbox: OutboxStore | None = None,
) -> TaskDispatcher:
    backend = settings.TASKS_DISPATCH_BACKEND

    if backend == "queue":
        if queue is None:
            raise RuntimeError("queue gateway required for queue task dispatcher")
        return QueueTaskDispatcher(queue)

    if backend == "outbox":
        if outbox is None:
            raise RuntimeError("outbox store required for outbox task dispatcher")
        return OutboxTaskDispatcher(outbox)

    raise ValueError(f"Unknown TASKS_DISPATCH_BACKEND={backend!r}")
