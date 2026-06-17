from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from app.bootstrap.resources import validate_core_resource_requirements
from app.core.config import Settings, get_settings
from app.core.database import build_engine, build_sessionmaker
from app.core.redis import build_redis_client
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.business.completions.pipeline import CompletionPipeline
from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.schemas import CompletionRequest
from app.modules.messaging.queue.factory import build_queue_gateway
from app.modules.messaging.queue.gateway import QueueMessage
from app.modules.messaging.queue.worker import AsyncPollingWorker
from app.modules.messaging.tasks.factory import build_task_store
from app.modules.messaging.tasks.service import TaskService

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.modules.messaging.queue.gateway import QueueGateway
    from app.modules.messaging.tasks.store import TaskStore


@dataclass
class WorkerResources:
    queue: QueueGateway
    store: TaskStore
    service: TaskService
    engine: AsyncEngine | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None
    redis: Redis | None = None


@dataclass
class WorkerContext:
    settings: Settings
    worker: AsyncPollingWorker
    handler: CompletionHandler
    pipeline: CompletionPipeline
    resources: WorkerResources


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
    from app.modules.messaging.tasks.factory import build_task_dispatcher

    outbox_store = None
    if settings.TASKS_DISPATCH_BACKEND == "outbox":
        if not settings.OUTBOX_ENABLED:
            raise RuntimeError("TASKS_DISPATCH_BACKEND=outbox requires OUTBOX_ENABLED")
        from app.modules.messaging.outbox.factory import build_outbox_store

        outbox_store = build_outbox_store(settings, sessionmaker=sessionmaker)

    dispatcher = build_task_dispatcher(settings, queue=queue, outbox=outbox_store)
    service = TaskService(
        store=store,
        dispatcher=dispatcher,
        ttl_seconds=settings.TASK_TTL_SECONDS,
        lease_seconds=settings.TASKS_LEASE_SECONDS,
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
    if resources.redis is not None:
        await resources.redis.aclose()
    if resources.engine is not None:
        await resources.engine.dispose()


def build_worker_context(
    settings: Settings | None = None,
    *,
    handler: CompletionHandler | None = None,
) -> WorkerContext:
    resolved = settings or get_settings()
    resources = build_worker_resources(resolved)
    resolved_handler: CompletionHandler = handler or EchoCompletionHandler()
    pipeline = CompletionPipeline(resolved_handler)
    worker = AsyncPollingWorker(
        gateway=resources.queue,
        handler=build_worker_message_handler(
            service=resources.service,
            pipeline=pipeline,
        ),
        max_concurrent=resolved.WORKER_MAX_CONCURRENT,
        max_attempts=resolved.WORKER_MAX_ATTEMPTS,
        poll_interval_seconds=resolved.WORKER_POLL_INTERVAL_SECONDS,
        receive_batch_size=resolved.WORKER_RECEIVE_BATCH_SIZE,
        receive_wait_seconds=resolved.WORKER_RECEIVE_WAIT_SECONDS,
    )
    return WorkerContext(
        settings=resolved,
        worker=worker,
        handler=resolved_handler,
        pipeline=pipeline,
        resources=resources,
    )


def build_worker_message_handler(
    *,
    service: TaskService,
    pipeline: CompletionPipeline,
) -> Callable[[QueueMessage], Awaitable[None]]:
    async def process_message(message: QueueMessage) -> None:
        task_id = message.body.get("task_id")
        if not task_id:
            logger.warning("worker.skip message_without_task_id={}", message.body)
            return

        try:
            task = await service.require(task_id)
        except Exception:
            logger.exception("worker.task_lookup_failed task_id={}", task_id)
            raise

        await service.mark_processing(task_id)
        try:
            payload = CompletionRequest(**task.payload)
            result = await pipeline.complete(payload)
            await service.mark_completed(
                task_id,
                {
                    "content": result.content,
                    "model": result.model,
                    "metadata": result.metadata,
                },
            )
            logger.info("worker.task_completed task_id={}", task_id)
        except Exception as exc:
            logger.exception("worker.task_failed task_id={}", task_id)
            await service.mark_failed(task_id, str(exc))
            raise

    return process_message


@asynccontextmanager
async def worker_context(
    settings: Settings | None = None,
    *,
    handler: CompletionHandler | None = None,
) -> AsyncIterator[WorkerContext]:
    ctx = build_worker_context(settings, handler=handler)
    try:
        yield ctx
    finally:
        await close_worker_resources(ctx.resources)


def check_worker_configuration(settings: Settings | None = None) -> None:
    validate_worker_runtime_settings(settings or get_settings())


def _worker_needs_database(settings: Settings) -> bool:
    return settings.DATABASE_ENABLED and settings.TASK_STORE_BACKEND == "postgres"


def _worker_needs_redis(settings: Settings) -> bool:
    return settings.REDIS_ENABLED and (
        settings.QUEUE_BACKEND == "redis" or settings.TASK_STORE_BACKEND == "redis"
    )
