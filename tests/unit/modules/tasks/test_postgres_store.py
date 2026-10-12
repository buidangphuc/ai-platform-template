"""PostgresTaskStore against the shared conformance contract.

Runs on SQLite always and on a real Postgres when ``TASKS_TEST_POSTGRES_URL``
(``postgresql+asyncpg://...``) is set (needed for real ``SKIP LOCKED``).
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.database.model import Base
from app.modules.messaging.tasks.adapters.postgres import PostgresTaskStore
from app.modules.messaging.tasks.models import Task
from app.modules.messaging.tasks.store import TaskStore

from .conformance import TaskStoreConformance

POSTGRES_URL = os.environ.get("TASKS_TEST_POSTGRES_URL")


class TestPostgresTaskStore(TaskStoreConformance):
    @pytest.fixture(params=["sqlite", "postgres"])
    def store_factory(self, request: pytest.FixtureRequest, tmp_path):
        if request.param == "postgres":
            if POSTGRES_URL is None:
                pytest.skip("TASKS_TEST_POSTGRES_URL not set")
            url = POSTGRES_URL
        else:
            url = f"sqlite+aiosqlite:///{tmp_path / 'tasks.db'}"

        async def _build() -> TaskStore:
            engine = create_async_engine(url)
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all, tables=[Task.__table__])
                await conn.run_sync(Base.metadata.create_all, tables=[Task.__table__])
            store = PostgresTaskStore(
                async_sessionmaker(engine, expire_on_commit=False)
            )
            original_close = store.close

            async def close() -> None:
                await original_close()
                await engine.dispose()

            store.close = close  # type: ignore[method-assign]
            return store

        return _build
