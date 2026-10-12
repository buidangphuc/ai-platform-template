"""Background loops that keep submitted tasks moving; owned by the worker process.

Both loops run until ``stop`` is set, survive a failing iteration (logged, retried
on the next tick), and are started by ``app/bootstrap/worker.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable

from loguru import logger

from app.modules.messaging.outbox.publisher import OutboxPublisher
from app.modules.messaging.tasks.service import TaskService


async def _every(
    interval_seconds: float,
    stop: asyncio.Event,
    name: str,
    step: Callable[[], Awaitable[None]],
) -> None:
    while not stop.is_set():
        try:
            await step()
        except Exception:
            logger.exception("tasks.{}_failed", name)
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(stop.wait(), timeout=interval_seconds)


async def run_outbox_relay(
    publisher: OutboxPublisher,
    *,
    interval_seconds: float,
    batch_size: int,
    stop: asyncio.Event,
) -> None:
    """Publish pending task outbox events to the queue."""

    async def step() -> None:
        report = await publisher.publish_pending(limit=batch_size)
        if report.total:
            logger.info(
                "tasks.outbox_relay published={} retried={} failed={}",
                report.published,
                report.retried,
                report.failed,
            )

    await _every(interval_seconds, stop, "outbox_relay", step)


async def run_reclaim_loop(
    service: TaskService,
    *,
    interval_seconds: float,
    batch_size: int,
    stop: asyncio.Event,
) -> None:
    """Requeue (and re-announce) tasks whose processing lease expired."""

    async def step() -> None:
        reclaimed = await service.reclaim_stale_processing(limit=batch_size)
        if reclaimed:
            logger.warning("tasks.reclaimed count={}", reclaimed)

    await _every(interval_seconds, stop, "reclaim", step)
