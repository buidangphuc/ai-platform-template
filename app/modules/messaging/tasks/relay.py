"""Background loops that keep tasks moving and tidy; owned by the worker process.

The loops run until ``stop`` is set, survive a failing iteration (logged, retried
on the next tick), and are started by ``app/bootstrap/worker.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from loguru import logger

from app.modules.messaging.outbox.publisher import OutboxPublisher
from app.modules.messaging.outbox.store import OutboxStore
from app.modules.messaging.tasks.service import TaskService
from app.modules.messaging.tasks.store import TaskStore


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
    max_attempts: int,
    stop: asyncio.Event,
) -> None:
    """Requeue (and re-announce) tasks whose processing lease expired.

    A task already claimed ``max_attempts`` times is failed instead.
    """

    async def step() -> None:
        reclaimed = await service.reclaim_stale_processing(
            limit=batch_size, max_attempts=max_attempts
        )
        if reclaimed:
            logger.warning("tasks.reclaimed count={}", reclaimed)

    await _every(interval_seconds, stop, "reclaim", step)


async def run_cleanup_loop(
    task_store: TaskStore,
    outbox_store: OutboxStore | None,
    *,
    interval_seconds: float,
    batch_size: int,
    outbox_retention_seconds: float,
    stop: asyncio.Event,
) -> None:
    """Purge expired tasks and, when an outbox exists, old published events.

    Deletes go in batches of ``batch_size`` and repeat until a batch comes back
    short, so a large backlog never holds one long-running DELETE.
    """

    async def step() -> None:
        now = datetime.now(UTC)
        tasks = await _drain(
            lambda: task_store.delete_expired(now, limit=batch_size), batch_size, stop
        )
        events = 0
        if outbox_store is not None:
            store = outbox_store
            cutoff = now - timedelta(seconds=outbox_retention_seconds)
            events = await _drain(
                lambda: store.delete_published_before(cutoff, limit=batch_size),
                batch_size,
                stop,
            )
        if tasks or events:
            logger.info("tasks.cleanup tasks={} outbox_events={}", tasks, events)

    await _every(interval_seconds, stop, "cleanup", step)


async def _drain(
    delete_batch: Callable[[], Awaitable[int]], batch_size: int, stop: asyncio.Event
) -> int:
    total = 0
    while not stop.is_set():
        deleted = await delete_batch()
        total += deleted
        if deleted < batch_size:
            break
    return total
