"""Standalone worker entry point.

Wires DB + queue gateway + task store + completion handler, then runs
``AsyncPollingWorker``. Lives outside the FastAPI lifespan so the worker can
scale independently of the API replicas.
"""

from __future__ import annotations

import asyncio

from loguru import logger

from app.api.v1.completions.handler import CompletionHandler
from app.api.v1.completions.schemas import (
    CompletionRequest,
    CompletionResult,
    CompletionStreamChunk,
)
from app.core.config import Settings, get_settings
from app.core.database import build_engine, build_sessionmaker
from app.core.logging import configure_logging
from app.core.redis import build_redis_client
from app.core.worker import AsyncPollingWorker
from app.modules.queue.factory import build_queue_gateway
from app.modules.queue.gateway import QueueMessage
from app.modules.tasks.factory import build_task_store
from app.modules.tasks.service import TaskService


class _EchoCompletionHandler:
    """Placeholder handler — replace via WORKER_HANDLER hook in real projects."""

    async def complete(self, request: CompletionRequest) -> CompletionResult:
        last = request.messages[-1].content
        return CompletionResult(content=f"echo: {last}", model="echo")

    async def stream(self, request: CompletionRequest):  # pragma: no cover
        yield CompletionStreamChunk(delta=f"echo: {request.messages[-1].content}")


def _build_completion_handler(settings: Settings) -> CompletionHandler:
    return _EchoCompletionHandler()


async def _run() -> None:
    settings = get_settings()
    configure_logging(level=settings.LOG_LEVEL, json_mode=settings.LOG_JSON)
    logger.info(
        "worker_entry queue_backend={} task_store_backend={}",
        settings.QUEUE_BACKEND,
        settings.TASK_STORE_BACKEND,
    )

    engine = build_engine(settings)
    sessionmaker = build_sessionmaker(engine)
    redis = build_redis_client(settings)
    queue = build_queue_gateway(settings, redis=redis)
    store = build_task_store(settings, sessionmaker=sessionmaker, redis=redis)
    service = TaskService(
        store=store, queue=queue, ttl_seconds=settings.TASK_TTL_SECONDS
    )
    handler = _build_completion_handler(settings)

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
            result = await handler.complete(payload)
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

    worker = AsyncPollingWorker(
        gateway=queue,
        handler=process_message,
        max_concurrent=settings.WORKER_MAX_CONCURRENT,
        poll_interval_seconds=settings.WORKER_POLL_INTERVAL_SECONDS,
        receive_batch_size=settings.WORKER_RECEIVE_BATCH_SIZE,
        receive_wait_seconds=settings.WORKER_RECEIVE_WAIT_SECONDS,
    )

    try:
        await worker.run()
    finally:
        await redis.aclose()
        await engine.dispose()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
