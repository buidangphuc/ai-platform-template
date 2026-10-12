import asyncio
from datetime import UTC, datetime, timedelta

from app.modules.messaging.queue.adapters.memory import InMemoryQueueGateway
from app.modules.messaging.tasks.adapters.memory import InMemoryTaskStore
from app.modules.messaging.tasks.relay import run_reclaim_loop
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

    async def flaky(*, now=None, limit=100):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("transient")
        return await real_reclaim(
            now=datetime.now(UTC) + timedelta(seconds=60), limit=limit
        )

    service.reclaim_stale_processing = flaky  # type: ignore[method-assign]
    stop = asyncio.Event()
    loop = asyncio.create_task(
        run_reclaim_loop(service, interval_seconds=0.01, batch_size=10, stop=stop)
    )
    [message] = await asyncio.wait_for(queue.receive(), timeout=2)
    stop.set()
    await asyncio.wait_for(loop, timeout=2)

    assert message.body == {"task_id": task.id, "type": "completion"}
    assert calls >= 2
