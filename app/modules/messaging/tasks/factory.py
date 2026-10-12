"""Build a ``TaskStore`` for the configured backend.

Memory needs nothing; postgres and redis take the client they need as a
required argument, so bootstrap passes exactly what the backend uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.messaging.tasks.store import TaskStore

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


def build_memory_task_store() -> TaskStore:
    from app.modules.messaging.tasks.adapters.memory import InMemoryTaskStore

    return InMemoryTaskStore()


def build_postgres_task_store(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> TaskStore:
    from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore

    return PostgresTaskStore(sessionmaker)


def build_redis_task_store(settings: Settings, redis: Redis) -> TaskStore:
    from app.modules.messaging.tasks.adapters.redis import RedisTaskStore

    return RedisTaskStore(redis=redis, prefix=settings.TASK_REDIS_PREFIX)
