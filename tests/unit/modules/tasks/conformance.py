"""Shared conformance contract every TaskStore adapter must satisfy."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import TaskRecord, TaskStore

StoreFactory = Callable[[], Awaitable[TaskStore]]


def _make_task(**overrides) -> TaskRecord:
    defaults = {
        "id": str(uuid4()),
        "type": "completion",
        "status": TaskStatus.QUEUED,
        "payload": {"prompt": "hello"},
        "expires_at": datetime.now(UTC) + timedelta(hours=1),
    }
    defaults.update(overrides)
    return TaskRecord(**defaults)


class TaskStoreConformance:
    @pytest.fixture
    async def store(self, store_factory: StoreFactory) -> AsyncIterator[TaskStore]:
        instance = await store_factory()
        try:
            yield instance
        finally:
            await instance.close()

    async def test_create_then_get_round_trip(self, store: TaskStore):
        task = _make_task()
        await store.create(task)

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.id == task.id
        assert fetched.type == "completion"
        assert fetched.status == TaskStatus.QUEUED
        assert fetched.payload == {"prompt": "hello"}

    async def test_get_returns_none_for_unknown_id(self, store: TaskStore):
        assert await store.get("does-not-exist") is None

    async def test_mark_processing_transitions_status_and_increments_attempts(
        self, store: TaskStore
    ):
        task = _make_task()
        await store.create(task)
        await store.mark_processing(task.id, lease_seconds=60)

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.status == TaskStatus.PROCESSING
        assert fetched.attempts == 1
        assert fetched.locked_until is not None

    async def test_reclaim_stale_processing_releases_expired_leases(
        self, store: TaskStore
    ):
        task = _make_task()
        await store.create(task)
        await store.mark_processing(task.id, lease_seconds=1)

        # Forward "now" past the lease window
        future_now = datetime.now(UTC) + timedelta(seconds=120)
        reclaimed = await store.reclaim_stale_processing(now=future_now)

        assert reclaimed >= 1
        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.status == TaskStatus.QUEUED
        assert fetched.locked_until is None

    async def test_mark_completed_persists_result(self, store: TaskStore):
        task = _make_task()
        await store.create(task)
        await store.mark_completed(task.id, {"answer": 42})

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.status == TaskStatus.COMPLETED
        assert fetched.result == {"answer": 42}

    async def test_mark_failed_persists_error(self, store: TaskStore):
        task = _make_task()
        await store.create(task)
        await store.mark_failed(task.id, "boom")

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.status == TaskStatus.FAILED
        assert fetched.error == "boom"

    async def test_delete_expired_removes_only_past_tasks(self, store: TaskStore):
        now = datetime.now(UTC)
        fresh = _make_task(expires_at=now + timedelta(hours=1))
        stale = _make_task(expires_at=now - timedelta(seconds=1))
        await store.create(fresh)
        await store.create(stale)

        deleted = await store.delete_expired(before=now)
        assert deleted >= 1
        assert await store.get(stale.id) is None
        assert await store.get(fresh.id) is not None
