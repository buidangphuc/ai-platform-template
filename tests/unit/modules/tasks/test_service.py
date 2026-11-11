from datetime import UTC, datetime, timedelta

import pytest

from app.core.errors import AppError
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.schemas import TaskSubmitResponse
from app.modules.messaging.tasks.service import QueueTaskDispatcher, TaskService
from app.modules.messaging.tasks.store import TaskStore


@pytest.fixture()
def service_parts(
    task_store: TaskStore, redis_queue: QueueGateway
) -> tuple[TaskService, QueueGateway, TaskStore]:
    store, queue = task_store, redis_queue
    service = TaskService(
        store=store,
        dispatcher=QueueTaskDispatcher(store, queue),
        ttl_seconds=3600,
    )
    return service, queue, store


async def test_submit_creates_task_and_enqueues_message(service_parts):
    service, queue, store = service_parts

    task = await service.submit(
        type="completion", payload={"prompt": "hi"}, principal_id="alice"
    )

    assert task.status == TaskStatus.QUEUED
    assert (await store.get(task.id)) is not None
    [message] = await queue.receive()
    assert message.body == {"task_id": task.id, "type": "completion"}


async def test_require_raises_not_found_for_unknown_task(service_parts):
    service, _, _ = service_parts

    with pytest.raises(AppError) as excinfo:
        await service.require("nope")
    assert excinfo.value.code == "task_not_found"
    assert excinfo.value.status_code == 404


async def test_submit_records_the_owning_principal(service_parts):
    service, _, store = service_parts

    task = await service.submit(type="completion", payload={}, principal_id="alice")

    assert task.principal_id == "alice"
    stored = await store.get(task.id)
    assert stored is not None and stored.principal_id == "alice"


async def test_require_owned_returns_the_owners_task(service_parts):
    service, _, _ = service_parts
    task = await service.submit(type="completion", payload={}, principal_id="alice")

    assert (
        await service.require_owned(task.id, principal_id="alice", type="completion")
    ).id == task.id


async def test_require_owned_hides_another_principals_task_as_not_found(service_parts):
    service, _, _ = service_parts
    task = await service.submit(type="completion", payload={}, principal_id="alice")

    with pytest.raises(AppError) as excinfo:
        await service.require_owned(task.id, principal_id="mallory", type="completion")
    assert excinfo.value.code == "task_not_found"
    assert excinfo.value.status_code == 404


async def test_require_owned_hides_another_task_type_as_not_found(service_parts):
    service, _, _ = service_parts
    task = await service.submit(type="other", payload={}, principal_id="alice")

    with pytest.raises(AppError) as excinfo:
        await service.require_owned(task.id, principal_id="alice", type="completion")
    assert excinfo.value.code == "task_not_found"


async def test_worker_require_is_owner_agnostic(service_parts):
    service, _, _ = service_parts
    task = await service.submit(type="completion", payload={}, principal_id="alice")

    assert (await service.require(task.id)).principal_id == "alice"


async def test_full_state_transitions_via_service(service_parts):
    service, _, store = service_parts
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


async def test_reclaim_stale_processing_via_service(
    task_store: TaskStore,
    redis_queue: QueueGateway,
):
    store, queue = task_store, redis_queue
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


async def test_submit_forwards_request_id_into_the_queue_message(service_parts):
    service, queue, _ = service_parts

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


async def test_submit_persists_the_request_id_on_the_task(service_parts):
    service, _, store = service_parts

    task = await service.submit(
        type="completion", payload={}, principal_id="alice", request_id="req_abc"
    )

    assert task.request_id == "req_abc"
    stored = await store.get(task.id)
    assert stored is not None and stored.request_id == "req_abc"


async def test_reclaimed_task_is_announced_with_its_original_request_id(
    task_store: TaskStore,
    redis_queue: QueueGateway,
):
    store, queue = task_store, redis_queue
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


async def test_submit_response_validates_from_the_task_record(service_parts):
    service, _, _ = service_parts
    task = await service.submit(
        type="completion", payload={"prompt": "hi"}, principal_id="alice"
    )

    response = TaskSubmitResponse.model_validate(task)

    assert response.model_dump()["task_id"] == task.id
