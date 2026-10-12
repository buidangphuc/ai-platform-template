"""Idempotency store concurrency tests.

They need a real Postgres (row locks / fenced UPDATE semantics cannot be
faked). Set ``IDEMPOTENCY_TEST_POSTGRES_URL`` (``postgresql+asyncpg://...``)
to run them; they are skipped otherwise.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.database.model import Base
from app.core.errors import AppError
from app.modules.platform.idempotency import service
from app.modules.platform.idempotency.adapters import PostgresIdempotencyStore
from app.modules.platform.idempotency.models import IdempotencyKey

POSTGRES_URL = os.environ.get("IDEMPOTENCY_TEST_POSTGRES_URL")
EXPIRES = datetime.now(UTC) + timedelta(hours=1)


@pytest_asyncio.fixture
async def sessionmaker() -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    if POSTGRES_URL is None:
        pytest.skip("IDEMPOTENCY_TEST_POSTGRES_URL not set")
    engine = create_async_engine(POSTGRES_URL)
    tables = [Base.metadata.tables["idempotency_keys"]]
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all, tables=tables)
        await conn.run_sync(Base.metadata.create_all, tables=tables)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


def _store(
    sessionmaker: async_sessionmaker[AsyncSession], *, timeout: int = 60
) -> PostgresIdempotencyStore:
    return PostgresIdempotencyStore(sessionmaker, in_progress_timeout_seconds=timeout)


async def _claim(store: PostgresIdempotencyStore, request_hash: str):
    return await store.check_or_store(
        key="k", principal_id="p", request_hash=request_hash, expires_at=EXPIRES
    )


async def _age_record(
    sessionmaker: async_sessionmaker[AsyncSession], *, seconds: int
) -> None:
    async with sessionmaker() as session, session.begin():
        await session.execute(
            update(IdempotencyKey).values(
                updated_at=datetime.now(UTC) - timedelta(seconds=seconds)
            )
        )


@pytest.fixture
def force_read_overlap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make concurrent claimers pause right after reading the record.

    Without a row lock every claimer reads the stale record and meets at the
    barrier, then they all reclaim. With the lock the others are blocked inside
    the read, never reach the barrier, and time out of it harmlessly.
    """
    barrier = asyncio.Barrier(2)
    original = service._find_record

    async def find_then_overlap(*args, **kwargs):
        record = await original(*args, **kwargs)
        try:
            async with asyncio.timeout(0.5):
                await barrier.wait()
        except (TimeoutError, asyncio.BrokenBarrierError):
            pass
        return record

    monkeypatch.setattr(service, "_find_record", find_then_overlap)


async def test_concurrent_retries_of_a_stuck_key_reclaim_it_once(
    sessionmaker, force_read_overlap
):
    store = _store(sessionmaker)
    await _claim(store, "h")
    await _age_record(sessionmaker, seconds=3600)

    results = await asyncio.gather(
        *[_claim(store, "h") for _ in range(2)], return_exceptions=True
    )

    reclaimed = [r for r in results if r is None]
    in_progress = [
        r for r in results if isinstance(r, AppError) and r.status_code == 409
    ]
    assert len(reclaimed) == 1
    assert len(in_progress) == 1


async def test_concurrent_retries_of_an_expired_key_reclaim_it_once(
    sessionmaker, force_read_overlap
):
    store = _store(sessionmaker)
    await _claim(store, "h")
    async with sessionmaker() as session, session.begin():
        await session.execute(
            update(IdempotencyKey).values(expires_at=datetime.now(UTC) - timedelta(1))
        )

    results = await asyncio.gather(
        *[_claim(store, "h") for _ in range(2)], return_exceptions=True
    )

    assert sum(r is None for r in results) == 1


async def test_late_original_cannot_overwrite_reclaiming_retry(sessionmaker):
    store = _store(sessionmaker)
    await _claim(store, "old-request")
    await _age_record(sessionmaker, seconds=3600)
    await _claim(store, "new-request")  # reclaims the key for a new request

    late = await store.store_response(
        key="k",
        principal_id="p",
        request_hash="old-request",
        status_code=200,
        response_body={"from": "original"},
    )
    winner = await store.store_response(
        key="k",
        principal_id="p",
        request_hash="new-request",
        status_code=201,
        response_body={"from": "retry"},
    )

    async with sessionmaker() as session:
        record = await session.scalar(select(IdempotencyKey))
    assert late is False
    assert winner is True
    assert record is not None
    assert record.response_body == {"from": "retry"}


async def test_completed_response_is_not_overwritten(sessionmaker):
    store = _store(sessionmaker)
    await _claim(store, "h")
    args = {"key": "k", "principal_id": "p", "request_hash": "h", "status_code": 200}

    first = await store.store_response(**args, response_body={"n": 1})
    second = await store.store_response(**args, response_body={"n": 2})

    async with sessionmaker() as session:
        record = await session.scalar(select(IdempotencyKey))
    assert (first, second) == (True, False)
    assert record is not None
    assert record.response_body == {"n": 1}
