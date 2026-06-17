from __future__ import annotations

from uuid import uuid4

from sqlalchemy import case, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.platform.quota.models import (
    QuotaReservation,
    QuotaReservationStatus,
    QuotaUsage,
    QuotaUsageQuery,
    ReserveQuota,
)
from app.modules.platform.quota.records import (
    QuotaCounter,
    QuotaReservationRecord,
)


class PostgresQuotaStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def reserve(self, command: ReserveQuota) -> QuotaReservation | None:
        async with self.sessionmaker() as session, session.begin():
            existing = await _find_idempotent_reservation(session, command)
            if existing is not None:
                return await _to_reservation(session, existing)

            await _ensure_counter(session, command)
            usage = await _try_increment_counter(session, command)
            if usage is None:
                return None

            record = QuotaReservationRecord(
                id=command.reservation_id,
                subject_id=command.subject_id,
                resource=command.resource,
                window_key=command.window_key,
                cost=command.cost,
                status=QuotaReservationStatus.RESERVED.value,
                idempotency_key=command.idempotency_key,
                reset_at=command.reset_at,
            )
            session.add(record)
            await session.flush()
            return QuotaReservation(
                id=record.id,
                subject_id=record.subject_id,
                resource=record.resource,
                window_key=record.window_key,
                cost=record.cost,
                status=QuotaReservationStatus(record.status),
                usage=usage,
                idempotency_key=record.idempotency_key,
            )

    async def finalize(self, reservation_id: str) -> QuotaUsage:
        async with self.sessionmaker() as session, session.begin():
            record = await _require_reservation(session, reservation_id)
            status = QuotaReservationStatus(record.status)
            if status == QuotaReservationStatus.REFUNDED:
                raise ValueError("refunded reservation cannot be finalized")
            if status == QuotaReservationStatus.RESERVED:
                record.status = QuotaReservationStatus.FINALIZED.value
                await session.flush()
            return await _usage_for_reservation(session, record)

    async def refund(self, reservation_id: str) -> QuotaUsage:
        async with self.sessionmaker() as session, session.begin():
            record = await _require_reservation(session, reservation_id)
            status = QuotaReservationStatus(record.status)
            if status == QuotaReservationStatus.FINALIZED:
                raise ValueError("finalized reservation cannot be refunded")
            if status == QuotaReservationStatus.REFUNDED:
                return await _usage_for_reservation(session, record)

            statement = (
                update(QuotaCounter)
                .where(
                    QuotaCounter.subject_id == record.subject_id,
                    QuotaCounter.resource == record.resource,
                    QuotaCounter.window_key == record.window_key,
                )
                .values(
                    used=case(
                        (
                            QuotaCounter.used >= record.cost,
                            QuotaCounter.used - record.cost,
                        ),
                        else_=0,
                    )
                )
                .returning(
                    QuotaCounter.subject_id,
                    QuotaCounter.resource,
                    QuotaCounter.window_key,
                    QuotaCounter.used,
                    QuotaCounter.limit,
                    QuotaCounter.reset_at,
                )
            )
            result = await session.execute(statement)
            row = result.one()
            record.status = QuotaReservationStatus.REFUNDED.value
            await session.flush()
            return _usage_from_row(row)

    async def get_usage(self, query: QuotaUsageQuery) -> QuotaUsage:
        async with self.sessionmaker() as session:
            statement = select(
                QuotaCounter.subject_id,
                QuotaCounter.resource,
                QuotaCounter.window_key,
                QuotaCounter.used,
                QuotaCounter.limit,
                QuotaCounter.reset_at,
            ).where(
                QuotaCounter.subject_id == query.subject_id,
                QuotaCounter.resource == query.resource,
                QuotaCounter.window_key == query.window_key,
            )
            result = await session.execute(statement)
            row = result.one_or_none()
            if row is None:
                return QuotaUsage(
                    subject_id=query.subject_id,
                    resource=query.resource,
                    window_key=query.window_key,
                    used=0,
                    limit=query.limit,
                    remaining=query.limit,
                    reset_at=query.reset_at,
                )
            return _usage_from_row(row)

    async def close(self) -> None:
        return None


async def _ensure_counter(session: AsyncSession, command: ReserveQuota) -> None:
    statement = (
        pg_insert(QuotaCounter)
        .values(
            id=str(uuid4()),
            subject_id=command.subject_id,
            resource=command.resource,
            window_key=command.window_key,
            used=0,
            limit=command.limit,
            reset_at=command.reset_at,
        )
        .on_conflict_do_update(
            index_elements=["subject_id", "resource", "window_key"],
            set_={
                "limit": command.limit,
                "reset_at": command.reset_at,
            },
        )
    )
    await session.execute(statement)


async def _try_increment_counter(
    session: AsyncSession,
    command: ReserveQuota,
) -> QuotaUsage | None:
    statement = (
        update(QuotaCounter)
        .where(
            QuotaCounter.subject_id == command.subject_id,
            QuotaCounter.resource == command.resource,
            QuotaCounter.window_key == command.window_key,
            QuotaCounter.used + command.cost <= command.limit,
        )
        .values(
            used=QuotaCounter.used + command.cost,
            limit=command.limit,
            reset_at=command.reset_at,
        )
        .returning(
            QuotaCounter.subject_id,
            QuotaCounter.resource,
            QuotaCounter.window_key,
            QuotaCounter.used,
            QuotaCounter.limit,
            QuotaCounter.reset_at,
        )
    )
    result = await session.execute(statement)
    row = result.one_or_none()
    return _usage_from_row(row) if row is not None else None


async def _find_idempotent_reservation(
    session: AsyncSession,
    command: ReserveQuota,
) -> QuotaReservationRecord | None:
    if command.idempotency_key is None:
        return None
    statement = select(QuotaReservationRecord).where(
        QuotaReservationRecord.subject_id == command.subject_id,
        QuotaReservationRecord.resource == command.resource,
        QuotaReservationRecord.window_key == command.window_key,
        QuotaReservationRecord.idempotency_key == command.idempotency_key,
    )
    return await session.scalar(statement)


async def _require_reservation(
    session: AsyncSession,
    reservation_id: str,
) -> QuotaReservationRecord:
    record = await session.get(QuotaReservationRecord, reservation_id)
    if record is None:
        raise KeyError(reservation_id)
    return record


async def _to_reservation(
    session: AsyncSession,
    record: QuotaReservationRecord,
) -> QuotaReservation:
    return QuotaReservation(
        id=record.id,
        subject_id=record.subject_id,
        resource=record.resource,
        window_key=record.window_key,
        cost=record.cost,
        status=QuotaReservationStatus(record.status),
        usage=await _usage_for_reservation(session, record),
        idempotency_key=record.idempotency_key,
    )


async def _usage_for_reservation(
    session: AsyncSession,
    record: QuotaReservationRecord,
) -> QuotaUsage:
    statement = select(
        QuotaCounter.subject_id,
        QuotaCounter.resource,
        QuotaCounter.window_key,
        QuotaCounter.used,
        QuotaCounter.limit,
        QuotaCounter.reset_at,
    ).where(
        QuotaCounter.subject_id == record.subject_id,
        QuotaCounter.resource == record.resource,
        QuotaCounter.window_key == record.window_key,
    )
    result = await session.execute(statement)
    return _usage_from_row(result.one())


def _usage_from_row(row) -> QuotaUsage:
    data = row._mapping
    used = int(data["used"])
    limit = int(data["limit"])
    return QuotaUsage(
        subject_id=data["subject_id"],
        resource=data["resource"],
        window_key=data["window_key"],
        used=used,
        limit=limit,
        remaining=max(limit - used, 0),
        reset_at=data["reset_at"],
    )
