"""Standalone async worker: same resource graph and handler factory as the API."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

from loguru import logger

from app.bootstrap.addons.base import BootstrapAddon, default_resource_addons
from app.bootstrap.resources import ApplicationResources, TaskServices, opened
from app.bootstrap.services import (
    CompletionGuardsFactory,
    CompletionHandlerFactory,
    default_completion_guards_factory,
    default_completion_handler_factory,
    open_runtime,
)
from app.core.config import Settings, get_settings
from app.modules.business.completions.schemas import CompletionRequest
from app.modules.business.completions.service import CompletionService
from app.modules.messaging.outbox.publisher import OutboxPublisher
from app.modules.messaging.queue.gateway import QueueMessage
from app.modules.messaging.queue.worker import (
    AsyncPollingWorker,
    NonRetryableMessageError,
)
from app.modules.messaging.tasks.message import TaskMessage
from app.modules.messaging.tasks.outbox import TASK_EVENT_PREFIX, TaskQueueOutboxSink
from app.modules.messaging.tasks.relay import (
    run_cleanup_loop,
    run_outbox_relay,
    run_reclaim_loop,
)
from app.modules.messaging.tasks.service import TaskService

# A background loop runs until the stop event is set.
BackgroundLoop = Callable[[asyncio.Event], Coroutine[Any, Any, None]]


@dataclass
class WorkerContext:
    settings: Settings
    worker: AsyncPollingWorker
    resources: ApplicationResources
    tasks: TaskServices
    loops: tuple[BackgroundLoop, ...]

    async def run(self) -> None:
        """Run the polling worker and the task housekeeping loops until shutdown.

        The loops stop when the worker stops (SIGTERM/SIGINT or a crash), so the
        process owns one lifetime for all of them.
        """
        stop = asyncio.Event()

        async def run_worker() -> None:
            try:
                await self.worker.run()
            finally:
                stop.set()

        async with asyncio.TaskGroup() as group:
            group.create_task(run_worker())
            for loop in self.loops:
                group.create_task(loop(stop))


def validate_worker_runtime_settings(settings: Settings) -> None:
    if not settings.QUEUE_ENABLED:
        raise RuntimeError("Worker requires QUEUE_ENABLED")
    if not settings.TASKS_ENABLED:
        raise RuntimeError("Worker requires TASKS_ENABLED")


def build_polling_worker(
    settings: Settings,
    *,
    tasks: TaskServices,
    completion_service: CompletionService,
) -> AsyncPollingWorker:
    return AsyncPollingWorker(
        gateway=tasks.queue,
        handler=build_worker_message_handler(
            service=tasks.service,
            completion_service=completion_service,
        ),
        max_concurrent=settings.WORKER_MAX_CONCURRENT,
        max_attempts=settings.WORKER_MAX_ATTEMPTS,
        poll_interval_seconds=settings.WORKER_POLL_INTERVAL_SECONDS,
        receive_batch_size=settings.WORKER_RECEIVE_BATCH_SIZE,
        receive_wait_seconds=settings.WORKER_RECEIVE_WAIT_SECONDS,
    )


def build_worker_message_handler(
    *,
    service: TaskService,
    completion_service: CompletionService,
) -> Callable[[QueueMessage], Awaitable[None]]:
    async def process_message(message: QueueMessage) -> None:
        task_id = TaskMessage.from_body(message.body).task_id

        try:
            task = await service.require(task_id)
        except Exception:
            logger.exception("worker.task_lookup_failed task_id={}", task_id)
            raise

        if not await service.mark_processing(task_id):
            logger.info("worker.skip task_id={} reason=not_claimable", task_id)
            return

        try:
            payload = CompletionRequest(**task.payload)
            result = await completion_service.complete(payload)
        except Exception as exc:
            logger.exception("worker.task_failed task_id={}", task_id)
            await service.mark_failed(task_id, _safe_error(exc))
            # FAILED is terminal: a redelivery would be skipped, so dead-letter now.
            raise NonRetryableMessageError(f"task {task_id} failed") from exc

        await service.mark_completed(
            task_id,
            {
                "content": result.content,
                "model": result.model,
                "metadata": result.metadata,
            },
        )
        logger.info("worker.task_completed task_id={}", task_id)

    return process_message


def _safe_error(exc: Exception) -> str:
    """What the API may show: the class name only; the detail stays in the logs."""
    return f"{type(exc).__name__}: task failed (see worker logs)"


def build_background_loops(
    settings: Settings,
    *,
    resources: ApplicationResources,
    tasks: TaskServices,
) -> tuple[BackgroundLoop, ...]:
    async def reclaim(stop: asyncio.Event) -> None:
        await run_reclaim_loop(
            tasks.service,
            interval_seconds=settings.TASKS_RECLAIM_INTERVAL_SECONDS,
            batch_size=settings.TASKS_RECLAIM_BATCH_SIZE,
            max_attempts=settings.TASKS_MAX_ATTEMPTS,
            stop=stop,
        )

    async def cleanup(stop: asyncio.Event) -> None:
        await run_cleanup_loop(
            tasks.store,
            resources.outbox_store,
            interval_seconds=settings.TASKS_CLEANUP_INTERVAL_SECONDS,
            batch_size=settings.TASKS_CLEANUP_BATCH_SIZE,
            outbox_retention_seconds=settings.OUTBOX_RETENTION_SECONDS,
            stop=stop,
        )

    match settings.TASKS_DISPATCH_BACKEND:
        case "queue":
            return (reclaim, cleanup)
        case "outbox":
            publisher = OutboxPublisher(
                store=opened(resources.outbox_store, "outbox store"),
                sink=TaskQueueOutboxSink(tasks.queue),
                event_type_prefix=TASK_EVENT_PREFIX,
            )

            async def relay(stop: asyncio.Event) -> None:
                await run_outbox_relay(
                    publisher,
                    interval_seconds=settings.TASKS_OUTBOX_RELAY_INTERVAL_SECONDS,
                    batch_size=settings.TASKS_OUTBOX_RELAY_BATCH_SIZE,
                    stop=stop,
                )

            return (relay, reclaim, cleanup)


@asynccontextmanager
async def worker_context(
    settings: Settings | None = None,
    *,
    completion_handler_factory: CompletionHandlerFactory = (
        default_completion_handler_factory
    ),
    completion_guards_factory: CompletionGuardsFactory = (
        default_completion_guards_factory
    ),
    addons: tuple[BootstrapAddon, ...] | None = None,
) -> AsyncIterator[WorkerContext]:
    resolved = settings or get_settings()
    validate_worker_runtime_settings(resolved)
    async with open_runtime(
        resolved,
        init_resources=True,
        addons=default_resource_addons() if addons is None else addons,
        completion_handler_factory=completion_handler_factory,
        completion_guards_factory=completion_guards_factory,
    ) as resources:
        # Guaranteed by validate_worker_runtime_settings (TASKS_ENABLED).
        tasks = opened(resources.tasks, "tasks")
        yield WorkerContext(
            settings=resolved,
            worker=build_polling_worker(
                resolved,
                tasks=tasks,
                completion_service=resources.completion_service,
            ),
            resources=resources,
            tasks=tasks,
            loops=build_background_loops(resolved, resources=resources, tasks=tasks),
        )


def check_worker_configuration(settings: Settings | None = None) -> None:
    validate_worker_runtime_settings(settings or get_settings())
