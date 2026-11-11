from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore
from app.modules.messaging.tasks.store import TaskStore

from .conformance import TaskStoreConformance


class TestPostgresTaskStore(TaskStoreConformance):
    @pytest.fixture
    def store_factory(self, pg_sessionmaker: async_sessionmaker[AsyncSession]):
        async def _build() -> TaskStore:
            return PostgresTaskStore(pg_sessionmaker)

        return _build
