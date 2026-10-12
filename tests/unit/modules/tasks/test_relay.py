import asyncio
from datetime import UTC, datetime, timedelta

from app.modules.messaging.queue.adapters.memory import InMemoryQueueGateway
from app.modules.messaging.tasks.adapters.memory import InMemoryTaskStore
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.relay import run_cleanup_loop, run_reclaim_loop
from app.modules.messaging.tasks.service import QueueTaskDispatcher, TaskService


async def test_reclaim_loop_requeues_expired_tasks_survives_errors_and_stops():
    store = InMemoryTaskStore()
    queue = InMemoryQueueGateway()
    service = TaskService(
        store=store,
        dispatcher=QueueTaskDispatcher(store, queue),
        ttl_seconds=3600,
        lease_seconds=1,
    )
    task = await service.submit(type="completion", payload={})
    await service.mark_processing(task.id)
    await queue.receive()  # drain the submit announcement

    real_reclaim = service.reclaim_stale_processing
    calls = 0

    async def flaky(*, now=None, limit=100, max_attempts):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return await real_reclaim(
            now=datetime.now(UTC) + timedelta(seconds=60),
            limit=limit,
            max_attempts=max_attempts,
        )

    service.reclaim_stale_processing = flaky  # type: ignore[method-assign]
    stop = asyncio.Event()
    loop = asyncio.create_task(
        run_reclaim_loop(
            service,
            interval_seconds=0.01,
            batch_size=10,
            max_attempts=5,
            stop=stop,
        )
    )
    [message] = await asyncio.wait_for(queue.receive(), timeout=2)
    stop.set()
    await asyncio.wait_for(loop, timeout=2)

    assert message.body == {"task_id": task.id, "type": "completion"}
    assert calls >= 2


async def test_cleanup_loop_purges_expired_tasks_and_old_published_events_in_batches():
    from app.modules.messaging.tasks.store import TaskRecord

    store = InMemoryTaskStore()
    now = datetime.now(UTC)
    for n in range(5):
        await store.create(
            TaskRecord(
                id=f"old-{n}",
                type="completion",
                status=TaskStatus.COMPLETED,
                payload={},
                expires_at=now - timedelta(seconds=1),
            )
        )
    await store.create(
        TaskRecord(
            id="fresh",
            type="completion",
            status=TaskStatus.QUEUED,
            payload={},
            expires_at=now + timedelta(hours=1),
        )
    )
    outbox = _CountingOutbox(pending_old_events=5)

    stop = asyncio.Event()
    loop = asyncio.create_task(
        run_cleanup_loop(
            store,
            outbox,  # type: ignore[arg-type]
            interval_seconds=0.01,
            batch_size=2,
            outbox_retention_seconds=3600,
            stop=stop,
        )
    )
    await asyncio.sleep(0.1)
    stop.set()
    await asyncio.wait_for(loop, timeout=2)

    assert [t for t in ("old-0", "old-4", "fresh") if await store.get(t)] == ["fresh"]
    assert outbox.remaining == 0
    assert outbox.batches[:3] == [2, 2, 1]  # drained batch by batch, never all at once
    assert all(
        datetime.now(UTC) - cutoff > timedelta(seconds=3590)
        for cutoff in outbox.cutoffs
    )


async def test_cleanup_loop_without_an_outbox_only_purges_tasks():
    store = InMemoryTaskStore()
    stop = asyncio.Event()
    loop = asyncio.create_task(
        run_cleanup_loop(
            store,
            None,
            interval_seconds=0.01,
            batch_size=10,
            outbox_retention_seconds=60,
            stop=stop,
        )
    )
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(loop, timeout=2)


class _CountingOutbox:
    def __init__(self, pending_old_events: int) -> None:
        self.remaining = pending_old_events
        self.batches: list[int] = []
        self.cutoffs: list[datetime] = []

    async def delete_published_before(self, before: datetime, *, limit: int) -> int:
        deleted = min(limit, self.remaining)
        self.remaining -= deleted
        self.batches.append(deleted)
        self.cutoffs.append(before)
        return deleted
