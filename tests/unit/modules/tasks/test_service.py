from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import AppError
from app.modules.messaging.queue.adapters.memory import InMemoryQueueGateway
from app.modules.messaging.tasks.adapters.memory import InMemoryTaskStore
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.service import QueueTaskDispatcher, TaskService


def _service() -> tuple[TaskService, InMemoryQueueGateway, InMemoryTaskStore]:
    store = InMemoryTaskStore()
    queue = InMemoryQueueGateway()
    service = TaskService(
        store=store,
        dispatcher=QueueTaskDispatcher(store, queue),
        ttl_seconds=3600,
    )
    return service, queue, store


async def test_submit_creates_task_and_enqueues_message():
    service, queue, store = _service()

    task = await service.submit(
        type="completion", payload={"prompt": "hi"}, principal_id="alice"
    )

    assert task.status == TaskStatus.QUEUED
    assert (await store.get(task.id)) is not None
    assert queue.pending_count() == 1
    [message] = await queue.receive()
    assert message.body == {"task_id": task.id, "type": "completion"}


async def test_require_raises_not_found_for_unknown_task():
    service, _, _ = _service()

    with pytest.raises(AppError) as excinfo:
        await service.require("nope")
    assert excinfo.value.code == "task_not_found"
    assert excinfo.value.status_code == 404


async def test_submit_records_the_owning_principal():
    service, _, store = _service()

    task = await service.submit(type="completion", payload={}, principal_id="alice")

    assert task.principal_id == "alice"
    stored = await store.get(task.id)
    assert stored is not None and stored.principal_id == "alice"


async def test_require_owned_returns_the_owners_task():
    service, _, _ = _service()
    task = await service.submit(type="completion", payload={}, principal_id="alice")

    assert (await service.require_owned(task.id, principal_id="alice")).id == task.id


async def test_require_owned_hides_another_principals_task_as_not_found():
    service, _, _ = _service()
    task = await service.submit(type="completion", payload={}, principal_id="alice")

    with pytest.raises(AppError) as excinfo:
        await service.require_owned(task.id, principal_id="mallory")
    assert excinfo.value.code == "task_not_found"
    assert excinfo.value.status_code == 404


async def test_worker_require_is_owner_agnostic():
    service, _, _ = _service()
    task = await service.submit(type="completion", payload={}, principal_id="alice")

    assert (await service.require(task.id)).principal_id == "alice"


async def test_full_state_transitions_via_service():
    service, _, store = _service()
    task = await service.submit(
        type="completion", payload={"q": 1}, principal_id="alice"
    )

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


async def test_reclaim_stale_processing_via_service():
    store = InMemoryTaskStore()
    queue = InMemoryQueueGateway()
    service = TaskService(
        store=store,
        dispatcher=QueueTaskDispatcher(store, queue),
        ttl_seconds=3600,
        lease_seconds=1,
    )

    task = await service.submit(type="completion", payload={}, principal_id="alice")
    await service.mark_processing(task.id)
    await queue.receive()  # drain the submit announcement

    reclaimed = await service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=120),
        max_attempts=5,
    )

    assert reclaimed == 1
    [message] = await queue.receive()
    assert message.body == {"task_id": task.id, "type": "completion"}
    refreshed = await store.get(task.id)
    assert refreshed is not None
    assert refreshed.status == TaskStatus.QUEUED


async def test_submit_forwards_request_id_into_the_queue_message():
    service, queue, _ = _service()

    task = await service.submit(
        type="completion",
        payload={"q": 1},
        principal_id="alice",
        request_id="req_abc",
    )

    [message] = await queue.receive()
    assert message.body == {
        "task_id": task.id,
        "type": "completion",
        "request_id": "req_abc",
    }


async def test_submit_persists_the_request_id_on_the_task():
    service, _, store = _service()

    task = await service.submit(
        type="completion", payload={}, principal_id="alice", request_id="req_abc"
    )

    assert task.request_id == "req_abc"
    stored = await store.get(task.id)
    assert stored is not None and stored.request_id == "req_abc"


async def test_reclaimed_task_is_announced_with_its_original_request_id():
    store = InMemoryTaskStore()
    queue = InMemoryQueueGateway()
    service = TaskService(
        store=store,
        dispatcher=QueueTaskDispatcher(store, queue),
        ttl_seconds=3600,
        lease_seconds=1,
    )
    task = await service.submit(
        type="completion", payload={}, principal_id="alice", request_id="req_abc"
    )
    await service.mark_processing(task.id)  # worker "crashes" holding the lease
    await queue.receive()  # drain the submit announcement

    await service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=120), max_attempts=5
    )

    [message] = await queue.receive()
    assert message.body == {
        "task_id": task.id,
        "type": "completion",
        "request_id": "req_abc",
    }
