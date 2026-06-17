from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import AppError
from app.modules.messaging.outbox.store import OutboxRecord, OutboxStatus
from app.modules.messaging.queue.adapters.memory import InMemoryQueueGateway
from app.modules.messaging.tasks.adapters.memory import InMemoryTaskStore
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.service import (
    OutboxTaskDispatcher,
    QueueTaskDispatcher,
    TaskService,
)


def _service() -> tuple[TaskService, InMemoryQueueGateway, InMemoryTaskStore]:
    store = InMemoryTaskStore()
    queue = InMemoryQueueGateway()
    service = TaskService(
        store=store,
        dispatcher=QueueTaskDispatcher(queue),
        ttl_seconds=3600,
    )
    return service, queue, store


async def test_submit_creates_task_and_enqueues_message():
    service, queue, store = _service()

    task = await service.submit(type="completion", payload={"prompt": "hi"})

    assert task.status == TaskStatus.QUEUED
    assert (await store.get(task.id)) is not None
    assert queue.pending_count() == 1


async def test_require_raises_not_found_for_unknown_task():
    service, _, _ = _service()

    with pytest.raises(AppError) as excinfo:
        await service.require("nope")
    assert excinfo.value.code == "task_not_found"
    assert excinfo.value.status_code == 404


async def test_full_state_transitions_via_service():
    service, _, store = _service()
    task = await service.submit(type="completion", payload={"q": 1})

    await service.mark_processing(task.id)
    in_progress = await store.get(task.id)
    assert in_progress is not None
    assert in_progress.status == TaskStatus.PROCESSING
    assert in_progress.locked_until is not None

    await service.mark_completed(task.id, {"answer": 2})
    fetched = await store.get(task.id)
    assert fetched is not None
    assert fetched.status == TaskStatus.COMPLETED
    assert fetched.result == {"answer": 2}
    assert fetched.locked_until is None


async def test_outbox_task_dispatcher_routes_through_outbox_store():
    class _FakeOutbox:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        async def enqueue(
            self,
            *,
            event_type: str,
            payload,
            metadata=None,
            available_at=None,
        ) -> OutboxRecord:
            self.events.append((event_type, dict(payload)))
            return OutboxRecord(
                id="evt-1",
                event_type=event_type,
                payload=dict(payload),
                status=OutboxStatus.PENDING,
                available_at=datetime.now(UTC),
            )

    outbox = _FakeOutbox()
    dispatcher = OutboxTaskDispatcher(outbox)

    await dispatcher.dispatch("task-42", type="completion")

    assert outbox.events == [
        ("task.completion", {"task_id": "task-42", "type": "completion"})
    ]


async def test_reclaim_stale_processing_via_service():
    store = InMemoryTaskStore()
    queue = InMemoryQueueGateway()
    service = TaskService(
        store=store,
        dispatcher=QueueTaskDispatcher(queue),
        ttl_seconds=3600,
        lease_seconds=1,
    )

    task = await service.submit(type="completion", payload={})
    await service.mark_processing(task.id)

    reclaimed = await service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=120),
    )

    assert reclaimed == 1
    refreshed = await store.get(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.QUEUED
