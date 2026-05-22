"""Standalone worker entry point.

Wires DB + queue gateway + task store + completion handler, then runs
``AsyncPollingWorker``. Lives outside the FastAPI lifespan so the worker can
scale independently of the API replicas.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger

from app.api.v1.completions.handler import CompletionHandler
from app.api.v1.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.bootstrap.worker import (
    WorkerResources,
    build_worker_resources,
    close_worker_resources,
    validate_worker_runtime_settings,
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.worker import AsyncPollingWorker
from app.modules.queue.gateway import QueueGateway, QueueMessage
from app.modules.tasks.service import TaskService
from app.modules.tasks.store import TaskStore

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine


class _EchoCompletionHandler:
    """Placeholder handler — replace via WORKER_HANDLER hook in real projects."""

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        last = request.messages[-1].content
        return CompletionResult(content=f"echo: {last}", model="echo")

    async def stream(self, request: CompletionRequest):  # pragma: no cover
        yield CompletionStreamChunk(delta=f"echo: {request.messages[-1].content}")


def _build_completion_handler(settings: Settings) -> CompletionHandler:
    return _EchoCompletionHandler()


@dataclass
class WorkerContext:
    settings: Settings
    worker: AsyncPollingWorker
    service: TaskService
    handler: CompletionHandler
    queue: QueueGateway
    store: TaskStore
    resources: WorkerResources
    engine: AsyncEngine | None
    redis: Redis | None


def build_worker_context(
    settings: Settings | None = None,
    *,
    handler: CompletionHandler | None = None,
) -> WorkerContext:
    resolved = settings or get_settings()
    resources = build_worker_resources(resolved)
    resolved_handler = handler or _build_completion_handler(resolved)

    async def process_message(message: QueueMessage) -> None:
        task_id = message.body.get("task_id")
        if not task_id:
            logger.warning("worker.skip message_without_task_id={}", message.body)
            return

        try:
            task = await resources.service.require(task_id)
        except Exception:
            logger.exception("worker.task_lookup_failed task_id={}", task_id)
            raise

        await resources.service.mark_processing(task_id)
        try:
            payload = CompletionRequest(**task.payload)
            result = await resolved_handler.complete(payload)
            await resources.service.mark_completed(
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
            await resources.service.mark_failed(task_id, str(exc))
            raise

    worker = AsyncPollingWorker(
        gateway=resources.queue,
        handler=process_message,
        max_concurrent=resolved.WORKER_MAX_CONCURRENT,
        max_attempts=resolved.WORKER_MAX_ATTEMPTS,
        poll_interval_seconds=resolved.WORKER_POLL_INTERVAL_SECONDS,
        receive_batch_size=resolved.WORKER_RECEIVE_BATCH_SIZE,
        receive_wait_seconds=resolved.WORKER_RECEIVE_WAIT_SECONDS,
    )

    return WorkerContext(
        settings=resolved,
        worker=worker,
        service=resources.service,
        handler=resolved_handler,
        queue=resources.queue,
        store=resources.store,
        resources=resources,
        engine=resources.engine,
        redis=resources.redis,
    )


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


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.LOG_LEVEL, json_mode=settings.LOG_JSON)
    logger.info(
        "worker_entry queue_backend={} task_store_backend={}",
        settings.QUEUE_BACKEND,
        settings.TASK_STORE_BACKEND,
    )
    async with worker_context(settings) as ctx:
        await ctx.worker.run()


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    if args == ["--check"]:
        try:
            check_worker_configuration()
        except Exception as exc:
            print(f"worker configuration invalid: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return
    if args:
        raise SystemExit(f"unknown arguments: {' '.join(args)}")
    asyncio.run(_run())


if __name__ == "__main__":
    main()
