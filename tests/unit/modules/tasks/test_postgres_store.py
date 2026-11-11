from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore
from app.modules.messaging.tasks.store import TaskStore

from .conformance import TaskStoreConformance, _make_task


class TestPostgresTaskStore(TaskStoreConformance):
    @pytest.fixture
    def store_factory(self, pg_sessionmaker: async_sessionmaker[AsyncSession]):
        async def _build() -> TaskStore:
            return PostgresTaskStore(pg_sessionmaker)

        return _build

    async def test_delete_expired_removes_only_past_tasks(self, store: TaskStore):
        now = datetime.now(UTC)
        fresh = _make_task(expires_at=now + timedelta(hours=1))
        stale = _make_task(expires_at=now - timedelta(seconds=1))
        await store.create(fresh)
        await store.create(stale)

        assert await store.delete_expired(before=now, limit=100) == 1
        assert await store.get(stale.id) is None
        assert await store.get(fresh.id) is not None

    async def test_delete_expired_respects_the_batch_limit(self, store: TaskStore):
        now = datetime.now(UTC)
        for _ in range(3):
            await store.create(_make_task(expires_at=now - timedelta(seconds=1)))

        first = await store.delete_expired(before=now, limit=2)
        second = await store.delete_expired(before=now, limit=2)

        assert (first, second) == (2, 1)
