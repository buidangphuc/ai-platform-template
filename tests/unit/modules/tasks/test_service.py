from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.errors import AppError
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore
from app.modules.messaging.tasks.adapters.redis import RedisTaskStore
from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.schemas import TaskSubmitResponse
from app.modules.messaging.tasks.service import TaskService
from app.modules.messaging.tasks.store import TaskStore
from tests.infra import require

from .queue_faults import fail_sends


@pytest.fixture(params=["postgres", "redis"])
async def task_store(
    request: pytest.FixtureRequest,
    pg_sessionmaker: async_sessionmaker[AsyncSession],
    redis_prefix: str,
) -> AsyncIterator[TaskStore]:
    if request.param == "postgres":
        yield PostgresTaskStore(pg_sessionmaker)
        return
    client = Redis.from_url(require("redis"), decode_responses=True)
    try:
        yield RedisTaskStore(redis=client, prefix=f"{redis_prefix}:tasks")
    finally:
        keys = [key async for key in client.scan_iter(match=f"{redis_prefix}*")]
        if keys:
            await client.delete(*keys)
        await client.aclose()


@pytest.fixture()
def service_parts(
    task_store: TaskStore, redis_queue: QueueGateway
) -> tuple[TaskService, QueueGateway, TaskStore]:
    store, queue = task_store, redis_queue
    service = TaskService(
        store=store,
        queue=queue,
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
        queue=queue,
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
        queue=queue,
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


async def test_submit_send_failure_leaves_task_queued_and_sweep_announces_it(
    task_store: TaskStore, redis_queue: QueueGateway, monkeypatch
):
    service = TaskService(store=task_store, queue=redis_queue, ttl_seconds=3600)
    faults = fail_sends(monkeypatch, redis_queue)

    task = await service.submit(
        type="completion", payload={}, principal_id="alice", request_id="req_abc"
    )

    assert faults.failed == [task.id]
    stored = await task_store.get(task.id)
    assert stored is not None and stored.status == TaskStatus.QUEUED
    assert await redis_queue.receive() == []

    faults.heal()
    swept = await service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=120), max_attempts=5
    )

    assert swept == 1
    [message] = await redis_queue.receive()
    assert message.body == {
        "task_id": task.id,
        "type": "completion",
        "request_id": "req_abc",
    }


async def test_reclaim_send_failure_is_repaired_by_a_later_sweep(
    task_store: TaskStore, redis_queue: QueueGateway, monkeypatch
):
    service = TaskService(
        store=task_store, queue=redis_queue, ttl_seconds=3600, lease_seconds=1
    )
    task = await service.submit(type="completion", payload={}, principal_id="alice")
    await service.mark_processing(task.id)
    await redis_queue.receive()
    faults = fail_sends(monkeypatch, redis_queue)
    first_tick = datetime.now(UTC) + timedelta(seconds=120)

    await service.reclaim_stale_processing(now=first_tick, max_attempts=5)

    assert faults.failed == [task.id]
    requeued = await task_store.get(task.id)
    assert requeued is not None and requeued.status == TaskStatus.QUEUED
    assert await redis_queue.receive() == []

    faults.heal()
    await service.reclaim_stale_processing(
        now=first_tick + timedelta(seconds=61), max_attempts=5
    )

    [message] = await redis_queue.receive()
    assert message.body == {"task_id": task.id, "type": "completion"}


async def test_sweep_announces_a_stale_task_once_per_interval(
    task_store: TaskStore, redis_queue: QueueGateway
):
    service = TaskService(store=task_store, queue=redis_queue, ttl_seconds=3600)
    task = await service.submit(type="completion", payload={}, principal_id="alice")
    await redis_queue.receive()
    tick = datetime.now(UTC) + timedelta(seconds=120)

    first = await service.reclaim_stale_processing(now=tick, max_attempts=5)
    second = await service.reclaim_stale_processing(
        now=tick + timedelta(seconds=10), max_attempts=5
    )
    third = await service.reclaim_stale_processing(
        now=tick + timedelta(seconds=61), max_attempts=5
    )

    assert (first, second, third) == (1, 0, 1)
    messages = await redis_queue.receive()
    assert [m.body["task_id"] for m in messages] == [task.id, task.id]


async def test_sweep_leaves_fresh_tasks_alone(
    task_store: TaskStore, redis_queue: QueueGateway
):
    service = TaskService(
        store=task_store,
        queue=redis_queue,
        ttl_seconds=3600,
        queued_reannounce_seconds=60,
    )
    await service.submit(type="completion", payload={}, principal_id="alice")
    await redis_queue.receive()

    swept = await service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=30), max_attempts=5
    )

    assert swept == 0
    assert await redis_queue.receive() == []


async def test_one_failed_send_does_not_stop_the_sweep(
    task_store: TaskStore, redis_queue: QueueGateway, monkeypatch
):
    service = TaskService(store=task_store, queue=redis_queue, ttl_seconds=3600)
    tasks = [
        await service.submit(type="completion", payload={}, principal_id="alice")
        for _ in range(3)
    ]
    await redis_queue.receive()
    faults = fail_sends(monkeypatch, redis_queue, task_ids={tasks[0].id})
    tick = datetime.now(UTC) + timedelta(seconds=120)

    await service.reclaim_stale_processing(now=tick, max_attempts=5)

    assert faults.failed == [tasks[0].id]
    delivered = await redis_queue.receive()
    assert {m.body["task_id"] for m in delivered} == {tasks[1].id, tasks[2].id}

    faults.heal()
    await service.reclaim_stale_processing(
        now=tick + timedelta(seconds=61), max_attempts=5
    )

    again = await redis_queue.receive()
    assert {m.body["task_id"] for m in again} == {t.id for t in tasks}


async def test_duplicate_announcement_runs_the_task_once(
    task_store: TaskStore, redis_queue: QueueGateway
):
    service = TaskService(store=task_store, queue=redis_queue, ttl_seconds=3600)
    task = await service.submit(type="completion", payload={}, principal_id="alice")
    await service.reclaim_stale_processing(
        now=datetime.now(UTC) + timedelta(seconds=120), max_attempts=5
    )

    messages = await redis_queue.receive()

    assert [m.body["task_id"] for m in messages] == [task.id, task.id]
    assert await service.mark_processing(task.id) is True
    assert await service.mark_processing(task.id) is False
