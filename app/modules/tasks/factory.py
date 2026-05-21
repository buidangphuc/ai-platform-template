"""Select a ``TaskStore`` implementation based on ``Settings.TASK_STORE_BACKEND``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.tasks.store import TaskStore

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
        from app.modules.tasks.adapters.memory import InMemoryTaskStore

        return InMemoryTaskStore()

    if backend == "postgres":
        if sessionmaker is None:
            raise RuntimeError("sessionmaker required for postgres task store")
        from app.modules.tasks.adapters.postgres import PostgresTaskStore

        return PostgresTaskStore(sessionmaker)

    if backend == "redis":
        if redis is None:
            raise RuntimeError("redis client required for redis task store")
        from app.modules.tasks.adapters.redis import RedisTaskStore

        return RedisTaskStore(redis=redis, prefix=settings.TASK_REDIS_PREFIX)

    raise ValueError(f"Unknown TASK_STORE_BACKEND={backend!r}")
