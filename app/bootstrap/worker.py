"""Standalone async worker: same resource graph and handler factory as the API."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

from loguru import logger

from app.bootstrap.addons.base import BootstrapAddon, default_resource_addons
from app.bootstrap.resources import (
    ApplicationResources,
    TaskServices,
    validate_core_resource_requirements,
)
from app.bootstrap.services import (
    CompletionHandlerFactory,
    default_completion_handler_factory,
    open_runtime,
)
from app.core.config import Settings, get_settings
from app.modules.business.completions.schemas import CompletionRequest
from app.modules.business.completions.service import CompletionService
from app.modules.messaging.queue.gateway import QueueMessage
from app.modules.messaging.queue.worker import AsyncPollingWorker
from app.modules.messaging.tasks.service import TaskService


@dataclass
class WorkerContext:
    settings: Settings
    worker: AsyncPollingWorker
    resources: ApplicationResources
    tasks: TaskServices


def validate_worker_runtime_settings(settings: Settings) -> None:
    if not settings.QUEUE_ENABLED:
        raise RuntimeError("Worker requires QUEUE_ENABLED")
    if not settings.TASKS_ENABLED:
        raise RuntimeError("Worker requires TASKS_ENABLED")
    validate_core_resource_requirements(settings=settings, init_resources=True)


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
            result = await completion_service.complete(payload)
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
    completion_handler_factory: CompletionHandlerFactory = (
        default_completion_handler_factory
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
    ) as resources:
        # Guaranteed by validate_worker_runtime_settings (TASKS_ENABLED).
        tasks = resources.tasks
        if tasks is None:
            raise RuntimeError("Worker requires TASKS_ENABLED")
        yield WorkerContext(
            settings=resolved,
            worker=build_polling_worker(
                resolved,
                tasks=tasks,
                completion_service=resources.completion_service,
            ),
            resources=resources,
            tasks=tasks,
        )


def check_worker_configuration(settings: Settings | None = None) -> None:
    validate_worker_runtime_settings(settings or get_settings())
