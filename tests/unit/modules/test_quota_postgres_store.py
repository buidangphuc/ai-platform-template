from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.database.model import Base
from app.modules.platform.quota.adapters.postgres import PostgresQuotaStore
from app.modules.platform.quota.models import QuotaReservationStatus, ReserveQuota
from app.modules.platform.quota.records import QuotaCounter, QuotaReservationRecord

RESET = datetime.now(UTC) + timedelta(minutes=5)


def test_alembic_env_imports_quota_records():
    env_source = Path("alembic/env.py").read_text()

    assert "app.modules.platform.quota import records" in env_source
    assert "quota_counters" in Base.metadata.tables
    assert "quota_reservations" in Base.metadata.tables


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


async def _used(pg_sessionmaker: async_sessionmaker[AsyncSession]) -> int:
    async with pg_sessionmaker() as session:
        return await session.scalar(select(QuotaCounter.used))  # type: ignore[return-value]


async def test_concurrent_refund_decrements_exactly_once(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)
    await store.reserve(_command("r1"))
    await store.reserve(_command("r2"))

    results = await asyncio.gather(
        store.refund("r1"), store.refund("r1"), return_exceptions=True
    )

    assert all(not isinstance(r, Exception) for r in results)
    assert await _used(pg_sessionmaker) == 1


async def test_concurrent_refund_and_finalize_single_winner(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)
    await store.reserve(_command("r1"))

    results = await asyncio.gather(
        store.refund("r1"), store.finalize("r1"), return_exceptions=True
    )

    errors = [r for r in results if isinstance(r, Exception)]
    assert len(errors) == 1 and isinstance(errors[0], ValueError)


async def test_concurrent_same_idempotency_key_returns_existing(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)

    first, second = await asyncio.gather(
        store.reserve(_command("a", key="k")),
        store.reserve(_command("b", key="k")),
    )

    assert first is not None and second is not None
    assert first.id == second.id
    assert await _used(pg_sessionmaker) == 1
    async with pg_sessionmaker() as session:
        count = len((await session.scalars(select(QuotaReservationRecord))).all())
    assert count == 1


async def test_reserve_over_limit_leaves_no_reservation_row(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)
    for index in range(5):
        assert await store.reserve(_command(f"r{index}")) is not None

    assert await store.reserve(_command("over")) is None

    async with pg_sessionmaker() as session:
        count = len((await session.scalars(select(QuotaReservationRecord))).all())
    assert count == 5
    assert await _used(pg_sessionmaker) == 5


async def test_upsert_refreshes_updated_at(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)
    await store.reserve(_command("r1"))
    async with pg_sessionmaker() as session:
        before = await session.scalar(select(QuotaCounter.updated_at))
    await asyncio.sleep(0.05)

    await store.reserve(_command("r2"))

    async with pg_sessionmaker() as session:
        after = await session.scalar(select(QuotaCounter.updated_at))
    assert after > before


async def test_retry_after_refund_charges_again(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)
    first = await store.reserve(_command("a", key="k"))
    assert first is not None
    await store.refund(first.id)

    retry = await store.reserve(_command("b", key="k"))

    assert retry is not None
    assert retry.id == first.id
    assert retry.status == QuotaReservationStatus.RESERVED
    assert retry.usage.used == 1
    assert await _used(pg_sessionmaker) == 1


async def test_retry_after_refund_is_rejected_at_the_limit(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)
    first = await store.reserve(_command("a", key="k"))
    assert first is not None
    await store.refund(first.id)
    for index in range(5):
        assert await store.reserve(_command(f"o{index}")) is not None

    retry = await store.reserve(_command("b", key="k"))

    assert retry is None
    assert await _used(pg_sessionmaker) == 5
    async with pg_sessionmaker() as session:
        status = await session.scalar(
            select(QuotaReservationRecord.status).where(
                QuotaReservationRecord.id == first.id
            )
        )
    assert status == QuotaReservationStatus.REFUNDED.value


async def test_concurrent_retries_after_refund_charge_once(pg_sessionmaker):
    store = PostgresQuotaStore(pg_sessionmaker)
    first = await store.reserve(_command("a", key="k"))
    assert first is not None
    await store.refund(first.id)

    retries = await asyncio.gather(
        *(store.reserve(_command(f"r{index}", key="k")) for index in range(5))
    )

    assert all(r is not None and r.id == first.id for r in retries)
    assert await _used(pg_sessionmaker) == 1
