from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.features.completions import completions_feature
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.worker import build_worker_message_handler
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.business.completions.service import CompletionService
from app.modules.messaging.outbox.adapters import PostgresOutboxStore, new_outbox_row
from app.modules.messaging.outbox.models import OutboxEvent
from app.modules.messaging.queue.adapters.redis_stream import RedisStreamQueueGateway
from app.modules.messaging.queue.worker import AsyncPollingWorker
from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.service import TaskService
from tests.unit.modules.tasks.queue_faults import fail_sends

PAYLOAD = {"messages": [{"role": "user", "content": "hello"}]}


class _Stack:
    def __init__(
        self,
        sessionmaker: async_sessionmaker[AsyncSession],
        queue: RedisStreamQueueGateway,
    ) -> None:
        self.sessionmaker = sessionmaker
        self.queue = queue
        self.store = PostgresTaskStore(sessionmaker)
        self.service = TaskService(
            store=self.store,
            queue=self.queue,
            ttl_seconds=3600,
            lease_seconds=1,
        )
        resources = ApplicationResources()
        resources.services[CompletionService] = CompletionService(
            EchoCompletionHandler()
        )
        self.worker = AsyncPollingWorker(
            gateway=self.queue,
            handler=build_worker_message_handler(
                service=self.service,
                resources=resources,
                handlers=completions_feature().tasks,
            ),
            poll_interval_seconds=0.01,
            receive_wait_seconds=0.05,
        )

    async def queue_is_empty(self) -> bool:
        return await self.queue.redis.xlen(self.queue.stream) == 0

    async def dead_letters(self) -> int:
        return await self.queue.redis.xlen(self.queue.dead_stream)

    async def wait_for_status(self, task_id: str, status: TaskStatus) -> None:
        for _ in range(200):
            task = await self.store.get(task_id)
            if task is not None and task.status == status:
                return
            await asyncio.sleep(0.02)
        pytest.fail(f"task {task_id} never reached {status}")


async def test_submitted_task_is_processed_and_completed(pg_sessionmaker, redis_queue):
    stack = _Stack(pg_sessionmaker, redis_queue)
    task = await stack.service.submit(
        type="completion", payload=PAYLOAD, principal_id="alice"
    )

    worker = asyncio.create_task(stack.worker.run())
    try:
        await stack.wait_for_status(task.id, TaskStatus.COMPLETED)
    finally:
        stack.worker.request_shutdown()
        await worker

    done = await stack.store.get(task.id)
    assert done is not None
    assert done.result == {
        "content": "echo: hello",
        "model": "echo",
        "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        "finish_reason": "stop",
        "metadata": {},
    }
    assert done.attempts == 1
    assert done.principal_id == "alice"
    assert await stack.dead_letters() == 0
    assert await stack.queue_is_empty()


async def test_lost_announcement_is_repaired_by_the_reclaim_sweep(
    pg_sessionmaker, redis_queue, monkeypatch
):
    stack = _Stack(pg_sessionmaker, redis_queue)
    faults = fail_sends(monkeypatch, redis_queue)
    task = await stack.service.submit(
        type="completion", payload=PAYLOAD, principal_id="alice"
    )
    assert faults.failed == [task.id]
    assert await stack.queue_is_empty()
    faults.heal()

    swept = await stack.service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=120), max_attempts=5
    )

    assert swept == 1
    worker = asyncio.create_task(stack.worker.run())
    try:
        await stack.wait_for_status(task.id, TaskStatus.COMPLETED)
    finally:
        stack.worker.request_shutdown()
        await worker

    done = await stack.store.get(task.id)
    assert done is not None and done.attempts == 1
    assert await stack.dead_letters() == 0
    assert await stack.queue_is_empty()


async def test_reclaimed_task_is_announced_again_with_its_original_request_id(
    pg_sessionmaker, redis_queue
):
    stack = _Stack(pg_sessionmaker, redis_queue)
    task = await stack.service.submit(
        type="completion",
        payload=PAYLOAD,
        principal_id="alice",
        request_id="req_abc",
    )
    [first] = await stack.queue.receive()
    await stack.queue.ack(first)
    assert await stack.service.mark_processing(task.id) is True  # worker "crashes"

    reclaimed = await stack.service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=60), max_attempts=5
    )

    assert reclaimed == 1
    [again] = await stack.queue.receive()
    assert again.body == {
        "task_id": task.id,
        "type": "completion",
        "request_id": "req_abc",
    }
    refreshed = await stack.store.get(task.id)
    assert refreshed is not None and refreshed.status == TaskStatus.QUEUED


async def test_redelivered_message_for_a_completed_task_is_acked_without_rerun(
    pg_sessionmaker, redis_queue
):
    stack = _Stack(pg_sessionmaker, redis_queue)
    task = await stack.service.submit(
        type="completion", payload=PAYLOAD, principal_id="alice"
    )
    await stack.queue.send({"task_id": task.id, "type": "completion"})

    worker = asyncio.create_task(stack.worker.run())
    try:
        await stack.wait_for_status(task.id, TaskStatus.COMPLETED)
        for _ in range(200):
            if await stack.queue_is_empty():
                break
            await asyncio.sleep(0.02)
    finally:
        stack.worker.request_shutdown()
        await worker

    done = await stack.store.get(task.id)
    assert done is not None and done.attempts == 1
    assert await stack.dead_letters() == 0


async def test_poison_task_is_failed_and_not_announced_again(
    pg_sessionmaker, redis_queue
):
    stack = _Stack(pg_sessionmaker, redis_queue)
    task = await stack.service.submit(
        type="completion", payload=PAYLOAD, principal_id="alice"
    )
    [first] = await stack.queue.receive()
    await stack.queue.ack(first)
    assert await stack.service.mark_processing(task.id) is True  # attempts = 1

    reclaimed = await stack.service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=60), max_attempts=1
    )

    assert reclaimed == 0
    refreshed = await stack.store.get(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.FAILED
    assert refreshed.error == "max_attempts_exceeded"
    assert await stack.queue.receive() == []
    async with pg_sessionmaker() as session:
        assert (await session.scalars(select(OutboxEvent))).all() == []


async def test_delete_published_before_purges_only_old_published_rows_in_batches(
    pg_sessionmaker,
):
    store = PostgresOutboxStore(pg_sessionmaker)
    now = datetime.now(UTC)
    old = now - timedelta(days=30)
    async with pg_sessionmaker() as session, session.begin():
        for n in range(3):
            row = new_outbox_row(event_type="task.completion", payload={"n": n})
            row.status = "published"
            row.published_at = old
            session.add(row)
        recent = new_outbox_row(event_type="task.completion", payload={})
        recent.status = "published"
        recent.published_at = now
        pending = new_outbox_row(event_type="task.completion", payload={})
        session.add_all([recent, pending])

    cutoff = now - timedelta(days=7)
    assert await store.delete_published_before(cutoff, limit=2) == 2
    assert await store.delete_published_before(cutoff, limit=2) == 1
    assert await store.delete_published_before(cutoff, limit=2) == 0

    async with pg_sessionmaker() as session:
        statuses = sorted(
            row.status for row in (await session.scalars(select(OutboxEvent))).all()
        )
    assert statuses == ["pending", "published"]
