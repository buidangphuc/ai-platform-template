"""PostgresQuotaStore concurrency tests.

They need a real Postgres (row locks / ON CONFLICT semantics cannot be faked).
Set ``QUOTA_TEST_POSTGRES_URL`` (``postgresql+asyncpg://...``) to run them;
they are skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database import Base
from app.modules.platform.quota.adapters.postgres import PostgresQuotaStore
from app.modules.platform.quota.models import ReserveQuota
from app.modules.platform.quota.records import QuotaCounter, QuotaReservationRecord

POSTGRES_URL = os.environ.get("QUOTA_TEST_POSTGRES_URL")
RESET = datetime.now(UTC) + timedelta(minutes=5)


def test_alembic_env_imports_quota_records():
    env_source = Path("alembic/env.py").read_text()

    assert "app.modules.platform.quota import records" in env_source
    assert "quota_counters" in Base.metadata.tables
    assert "quota_reservations" in Base.metadata.tables


@pytest_asyncio.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if POSTGRES_URL is None:
        pytest.skip("QUOTA_TEST_POSTGRES_URL not set")
    engine = create_async_engine(POSTGRES_URL)
    tables = [
        Base.metadata.tables["quota_counters"],
        Base.metadata.tables["quota_reservations"],
    ]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=tables)
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _command(reservation_id: str, *, key: str | None = None) -> ReserveQuota:
    return ReserveQuota(
        subject_id="s",
        resource="r",
        window_key="w1",
        limit=5,
        cost=1,
        reset_at=RESET,
        reservation_id=reservation_id,
        idempotency_key=key,
    )


async def _used(sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with sessionmaker() as session:
        return await session.scalar(select(QuotaCounter.used))  # type: ignore[return-value]


async def test_concurrent_refund_decrements_exactly_once(sessionmaker):
    store = PostgresQuotaStore(sessionmaker)
    await store.reserve(_command("r1"))
    await store.reserve(_command("r2"))

    results = await asyncio.gather(
        store.refund("r1"), store.refund("r1"), return_exceptions=True
    )

    assert all(not isinstance(r, Exception) for r in results)
    assert await _used(sessionmaker) == 1


async def test_concurrent_refund_and_finalize_single_winner(sessionmaker):
    store = PostgresQuotaStore(sessionmaker)
    await store.reserve(_command("r1"))

    results = await asyncio.gather(
        store.refund("r1"), store.finalize("r1"), return_exceptions=True
    )

    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1 and isinstance(errors[0], ValueError)


async def test_concurrent_same_idempotency_key_returns_existing(sessionmaker):
    store = PostgresQuotaStore(sessionmaker)

    first, second = await asyncio.gather(
        store.reserve(_command("a", key="k")),
        store.reserve(_command("b", key="k")),
    )

    assert first is not None and second is not None
    assert first.id == second.id
    assert await _used(sessionmaker) == 1
    async with sessionmaker() as session:
        count = len((await session.scalars(select(QuotaReservationRecord))).all())
    assert count == 1


async def test_reserve_over_limit_leaves_no_reservation_row(sessionmaker):
    store = PostgresQuotaStore(sessionmaker)
    for index in range(5):
        assert await store.reserve(_command(f"r{index}")) is not None

    assert await store.reserve(_command("over")) is None

    async with sessionmaker() as session:
        count = len((await session.scalars(select(QuotaReservationRecord))).all())
    assert count == 5
    assert await _used(sessionmaker) == 5


async def test_upsert_refreshes_updated_at(sessionmaker):
    store = PostgresQuotaStore(sessionmaker)
    await store.reserve(_command("r1"))
    async with sessionmaker() as session:
        before = await session.scalar(select(QuotaCounter.updated_at))
    await asyncio.sleep(0.05)

    await store.reserve(_command("r2"))

    async with sessionmaker() as session:
        after = await session.scalar(select(QuotaCounter.updated_at))
    assert after > before
