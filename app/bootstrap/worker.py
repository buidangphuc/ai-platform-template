from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.bootstrap.resources import validate_core_resource_requirements
from app.core.config import Settings
from app.core.database import build_engine, build_sessionmaker
from app.core.redis import build_redis_client
from app.modules.queue.factory import build_queue_gateway
from app.modules.tasks.factory import build_task_store
from app.modules.tasks.service import TaskService

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.modules.queue.gateway import QueueGateway
    from app.modules.tasks.store import TaskStore


@dataclass
class WorkerResources:
    queue: QueueGateway
    store: TaskStore
    service: TaskService
    engine: AsyncEngine | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None
    redis: Redis | None = None


def validate_worker_runtime_settings(settings: Settings) -> None:
    if not settings.QUEUE_ENABLED:
        raise RuntimeError("Worker requires QUEUE_ENABLED")
    if not settings.TASKS_ENABLED:
        raise RuntimeError("Worker requires TASKS_ENABLED")
    validate_core_resource_requirements(settings=settings, init_resources=True)


def build_worker_resources(settings: Settings) -> WorkerResources:
    validate_worker_runtime_settings(settings)
    engine = None
    sessionmaker = None
    redis = None

    if _worker_needs_database(settings):
        engine = build_engine(settings)
        sessionmaker = build_sessionmaker(engine)

    if _worker_needs_redis(settings):
        redis = build_redis_client(settings)

    queue = build_queue_gateway(settings, redis=redis)
    store = build_task_store(settings, sessionmaker=sessionmaker, redis=redis)
    service = TaskService(
        store=store,
        queue=queue,
        ttl_seconds=settings.TASK_TTL_SECONDS,
    )
    return WorkerResources(
        engine=engine,
        sessionmaker=sessionmaker,
        redis=redis,
        queue=queue,
        store=store,
        service=service,
    )


async def close_worker_resources(resources: WorkerResources) -> None:
    await resources.queue.close()
    await resources.store.close()
    if resources.redis is not None and hasattr(resources.redis, "aclose"):
        await resources.redis.aclose()
    if resources.engine is not None:
        await resources.engine.dispose()


def _worker_needs_database(settings: Settings) -> bool:
    return settings.DATABASE_ENABLED and settings.TASK_STORE_BACKEND == "postgres"


def _worker_needs_redis(settings: Settings) -> bool:
    return settings.REDIS_ENABLED and (
        settings.QUEUE_BACKEND == "redis" or settings.TASK_STORE_BACKEND == "redis"
    )
