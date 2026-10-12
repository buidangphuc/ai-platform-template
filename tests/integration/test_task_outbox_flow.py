"""submit -> outbox -> relay -> queue -> worker -> COMPLETED, end to end.

Runs on SQLite always (same SQLAlchemy code path, RETURNING/IN-subquery work) and
additionally on a real Postgres when ``TASKS_TEST_POSTGRES_URL``
(``postgresql+asyncpg://...``) is set, where ``FOR UPDATE SKIP LOCKED`` is real.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.bootstrap.worker import build_worker_message_handler
from app.core.database.model import Base
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.business.completions.service import CompletionService
from app.modules.messaging.outbox.adapters import PostgresOutboxStore
from app.modules.messaging.outbox.models import OutboxEvent
from app.modules.messaging.outbox.publisher import OutboxPublisher
from app.modules.messaging.queue.adapters.memory import InMemoryQueueGateway
from app.modules.messaging.queue.worker import AsyncPollingWorker
from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore
from app.modules.messaging.tasks.models import Task, TaskStatus
from app.modules.messaging.tasks.outbox import (
    TASK_EVENT_PREFIX,
    PostgresTaskOutboxDispatcher,
    TaskQueueOutboxSink,
)
from app.modules.messaging.tasks.relay import run_outbox_relay
from app.modules.messaging.tasks.service import TaskService

POSTGRES_URL = os.environ.get("TASKS_TEST_POSTGRES_URL")
PAYLOAD = {"messages": [{"role": "user", "content": "hello"}]}


@pytest_asyncio.fixture(params=["sqlite", "postgres"])
async def sessionmaker(
    request: pytest.FixtureRequest, tmp_path: Path
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if request.param == "postgres":
        if POSTGRES_URL is None:
            pytest.skip("TASKS_TEST_POSTGRES_URL not set")
        url = POSTGRES_URL
    else:
        url = f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}"
    engine = create_async_engine(url)
    tables = [Task.__table__, OutboxEvent.__table__]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=tables)
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


class _Stack:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker
        self.queue = InMemoryQueueGateway()
        self.store = PostgresTaskStore(sessionmaker)
        self.service = TaskService(
            store=self.store,
            dispatcher=PostgresTaskOutboxDispatcher(sessionmaker),
            ttl_seconds=3600,
            lease_seconds=1,
        )
        self.publisher = OutboxPublisher(
            store=PostgresOutboxStore(sessionmaker),
            sink=TaskQueueOutboxSink(self.queue),
            event_type_prefix=TASK_EVENT_PREFIX,
        )
        self.worker = AsyncPollingWorker(
            gateway=self.queue,
            handler=build_worker_message_handler(
                service=self.service,
                completion_service=CompletionService(EchoCompletionHandler()),
            ),
            poll_interval_seconds=0.01,
            receive_wait_seconds=0.05,
        )

    async def wait_for_status(self, task_id: str, status: TaskStatus) -> None:
        for _ in range(200):
            task = await self.store.get(task_id)
            if task is not None and task.status == status:
                return
            await asyncio.sleep(0.02)
        pytest.fail(f"task {task_id} never reached {status}")


async def test_submitted_task_is_relayed_processed_and_completed(sessionmaker):
    stack = _Stack(sessionmaker)
    task = await stack.service.submit(type="completion", payload=PAYLOAD)
    stop = asyncio.Event()

    relay = asyncio.create_task(
        run_outbox_relay(
            stack.publisher, interval_seconds=0.02, batch_size=10, stop=stop
        )
    )
    worker = asyncio.create_task(stack.worker.run())
    try:
        await stack.wait_for_status(task.id, TaskStatus.COMPLETED)
    finally:
        stop.set()
        stack.worker.request_shutdown()
        await asyncio.gather(relay, worker)

    done = await stack.store.get(task.id)
    assert done is not None
    assert done.result == {"content": "echo: hello", "model": "echo", "metadata": {}}
    assert done.attempts == 1
    assert stack.queue.dead_letter_count() == 0
    assert stack.queue.pending_count() == 0 and stack.queue.inflight_count() == 0


async def test_task_row_and_outbox_event_commit_atomically(sessionmaker, monkeypatch):
    stack = _Stack(sessionmaker)

    def _boom(*args, **kwargs):
        raise RuntimeError("outbox insert failed")

    monkeypatch.setattr("app.modules.messaging.tasks.outbox.new_outbox_row", _boom)

    with pytest.raises(RuntimeError, match="outbox insert failed"):
        await stack.service.submit(type="completion", payload=PAYLOAD)

    async with sessionmaker() as session:
        assert (await session.scalars(select(Task))).all() == []
        assert (await session.scalars(select(OutboxEvent))).all() == []


async def test_reclaimed_task_is_announced_again_in_the_same_transaction(sessionmaker):
    stack = _Stack(sessionmaker)
    task = await stack.service.submit(type="completion", payload=PAYLOAD)
    await stack.publisher.publish_pending()
    [first] = await stack.queue.receive()
    await stack.queue.ack(first)
    assert await stack.service.mark_processing(task.id) is True  # worker "crashes"

    reclaimed = await stack.service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=60)
    )
    assert reclaimed == 1
    report = await stack.publisher.publish_pending()

    assert report.published == 1
    [again] = await stack.queue.receive()
    assert again.body == {"task_id": task.id, "type": "completion"}
    refreshed = await stack.store.get(task.id)
    assert refreshed is not None and refreshed.status == TaskStatus.QUEUED


async def test_redelivered_message_for_a_completed_task_is_acked_without_rerun(
    sessionmaker,
):
    stack = _Stack(sessionmaker)
    task = await stack.service.submit(type="completion", payload=PAYLOAD)
    await stack.publisher.publish_pending()
    # The same announcement delivered twice (at-least-once queue).
    await stack.queue.send({"task_id": task.id, "type": "completion"})

    worker = asyncio.create_task(stack.worker.run())
    try:
        await stack.wait_for_status(task.id, TaskStatus.COMPLETED)
        for _ in range(200):
            if stack.queue.pending_count() == 0 and stack.queue.inflight_count() == 0:
                break
            await asyncio.sleep(0.02)
    finally:
        stack.worker.request_shutdown()
        await worker

    done = await stack.store.get(task.id)
    assert done is not None and done.attempts == 1
    assert stack.queue.dead_letter_count() == 0
