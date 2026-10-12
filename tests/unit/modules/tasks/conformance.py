"""Shared conformance contract every TaskStore adapter must satisfy."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from app.modules.messaging.tasks.models import TaskStatus
from app.modules.messaging.tasks.store import (
    MAX_ATTEMPTS_EXCEEDED,
    TaskRecord,
    TaskStore,
)

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

    async def test_principal_id_round_trips(self, store: TaskStore):
        task = _make_task(principal_id="alice")
        await store.create(task)

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.principal_id == "alice"

    async def test_get_scoped_to_principal_hides_other_owners_tasks(
        self, store: TaskStore
    ):
        task = _make_task(principal_id="alice")
        await store.create(task)

        mine = await store.get(task.id, principal_id="alice")
        theirs = await store.get(task.id, principal_id="mallory")
        worker = await store.get(task.id)

        assert mine is not None and mine.id == task.id
        assert theirs is None
        assert worker is not None  # unscoped (worker) reads see every task

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
        reclaimed = await store.reclaim_stale_processing(now=future_now, max_attempts=5)

        assert [ref.id for ref in reclaimed] == [task.id]
        assert reclaimed[0].type == "completion"
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

        deleted = await store.delete_expired(before=now, limit=100)
        assert deleted >= 1
        assert await store.get(stale.id) is None
        assert await store.get(fresh.id) is not None

    async def test_mark_processing_refuses_a_live_lease(self, store: TaskStore):
        task = _make_task()
        await store.create(task)
        assert await store.mark_processing(task.id, lease_seconds=60) is True

        assert await store.mark_processing(task.id, lease_seconds=60) is False

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.attempts == 1

    async def test_mark_processing_takes_over_an_expired_lease(self, store: TaskStore):
        task = _make_task()
        await store.create(task)
        await store.mark_processing(task.id, lease_seconds=1)

        later = datetime.now(UTC) + timedelta(seconds=120)
        assert await store.mark_processing(task.id, lease_seconds=60, now=later) is True

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.attempts == 2

    @pytest.mark.parametrize("terminal", ["completed", "failed"])
    async def test_mark_processing_never_revives_a_terminal_task(
        self, store: TaskStore, terminal: str
    ):
        task = _make_task()
        await store.create(task)
        if terminal == "completed":
            await store.mark_completed(task.id, {"answer": 1})
        else:
            await store.mark_failed(task.id, "boom")

        assert await store.mark_processing(task.id, lease_seconds=60) is False

        fetched = await store.get(task.id)
        assert fetched is not None
        assert fetched.status.value == terminal

    async def test_mark_processing_unknown_task_raises(self, store: TaskStore):
        with pytest.raises(KeyError):
            await store.mark_processing("missing", lease_seconds=60)

    async def test_reclaim_respects_limit_and_skips_live_leases(self, store: TaskStore):
        expired = [_make_task() for _ in range(3)]
        live = _make_task()
        for task in (*expired, live):
            await store.create(task)
        for task in expired:
            await store.mark_processing(task.id, lease_seconds=1)
        await store.mark_processing(live.id, lease_seconds=3600)

        later = datetime.now(UTC) + timedelta(seconds=120)
        first = await store.reclaim_stale_processing(now=later, limit=2, max_attempts=5)
        second = await store.reclaim_stale_processing(
            now=later, limit=2, max_attempts=5
        )

        assert len(first) == 2
        assert len(second) == 1
        assert {ref.id for ref in (*first, *second)} == {t.id for t in expired}
        still_live = await store.get(live.id)
        assert still_live is not None
        assert still_live.status == TaskStatus.PROCESSING

    async def test_reclaim_fails_a_task_that_used_up_its_attempts(
        self, store: TaskStore
    ):
        poison = _make_task()
        healthy = _make_task()
        for task in (poison, healthy):
            await store.create(task)
        await store.mark_processing(healthy.id, lease_seconds=1)  # attempts = 1
        start = datetime.now(UTC) - timedelta(seconds=60)
        for n in range(3):  # claimed, "crashed", lease expired, claimed again
            await store.mark_processing(
                poison.id, lease_seconds=1, now=start + timedelta(seconds=10 * n)
            )

        later = datetime.now(UTC) + timedelta(seconds=120)
        reclaimed = await store.reclaim_stale_processing(now=later, max_attempts=3)

        assert [ref.id for ref in reclaimed] == [healthy.id]
        failed = await store.get(poison.id)
        assert failed is not None
        assert failed.status == TaskStatus.FAILED
        assert failed.error == MAX_ATTEMPTS_EXCEEDED
        assert failed.locked_until is None
        requeued = await store.get(healthy.id)
        assert requeued is not None and requeued.status == TaskStatus.QUEUED
        # Terminal: a later pass and a late claim both leave it alone.
        assert await store.reclaim_stale_processing(now=later, max_attempts=3) == []
        assert await store.mark_processing(poison.id, lease_seconds=60) is False

    async def test_reclaim_limit_counts_failed_tasks_too(self, store: TaskStore):
        tasks = [_make_task() for _ in range(3)]
        for task in tasks:
            await store.create(task)
            await store.mark_processing(task.id, lease_seconds=1)

        later = datetime.now(UTC) + timedelta(seconds=120)
        assert (
            await store.reclaim_stale_processing(now=later, limit=2, max_attempts=1)
            == []
        )
        assert (
            await store.reclaim_stale_processing(now=later, limit=2, max_attempts=1)
            == []
        )
        statuses = [(await store.get(t.id)).status for t in tasks]  # type: ignore[union-attr]
        assert statuses == [TaskStatus.FAILED] * 3

    async def test_delete_expired_respects_the_batch_limit(self, store: TaskStore):
        now = datetime.now(UTC)
        stale = [_make_task(expires_at=now - timedelta(seconds=1)) for _ in range(3)]
        for task in stale:
            await store.create(task)

        first = await store.delete_expired(before=now, limit=2)
        second = await store.delete_expired(before=now, limit=2)

        # Redis expires by TTL and reports 0 (see its module docstring).
        assert (first, second) in {(2, 1), (0, 0)}
