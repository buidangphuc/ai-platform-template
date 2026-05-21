import pytest

from app.core.errors import AppError
from app.modules.queue.adapters.memory import InMemoryQueueGateway
from app.modules.tasks.adapters.memory import InMemoryTaskStore
from app.modules.tasks.models import TaskStatus
from app.modules.tasks.service import TaskService


def _service() -> tuple[TaskService, InMemoryQueueGateway, InMemoryTaskStore]:
    store = InMemoryTaskStore()
    queue = InMemoryQueueGateway()
    service = TaskService(store=store, queue=queue, ttl_seconds=3600)
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

    await service.mark_completed(task.id, {"answer": 2})
    fetched = await store.get(task.id)
    assert fetched is not None
    assert fetched.status == TaskStatus.COMPLETED
    assert fetched.result == {"answer": 2}
