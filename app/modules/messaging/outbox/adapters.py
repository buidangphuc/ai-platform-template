from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.messaging.outbox.models import OutboxEvent
from app.modules.messaging.outbox.store import OutboxRecord, OutboxStatus


class PostgresOutboxStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def enqueue(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        available_at: datetime | None = None,
    ) -> OutboxRecord:
        event = new_outbox_row(
            event_type=event_type,
            payload=payload,
            metadata=metadata,
            available_at=available_at,
        )
        async with self.sessionmaker() as session, session.begin():
            session.add(event)
            await session.flush()
            return _to_record(event)

    async def list_pending(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> Sequence[OutboxRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        now = now or datetime.now(UTC)
        stmt = _pending_stmt(limit=limit, now=now)
        async with self.sessionmaker() as session:
            rows = (await session.scalars(stmt)).all()
            return [_to_record(row) for row in rows]

    async def claim_pending(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
        lock_seconds: float = 60.0,
        event_type_prefix: str | None = None,
    ) -> Sequence[OutboxRecord]:
        if limit <= 0:
            raise ValueError("limit must be positive")
        if lock_seconds <= 0:
            raise ValueError("lock_seconds must be positive")
        now = now or datetime.now(UTC)
        locked_until = now + timedelta(seconds=lock_seconds)
        stmt = _pending_stmt(
            limit=limit, now=now, event_type_prefix=event_type_prefix
        ).with_for_update(skip_locked=True)
        async with self.sessionmaker() as session, session.begin():
            rows = (await session.scalars(stmt)).all()
            for row in rows:
                row.locked_until = locked_until
            await session.flush()
            return [_to_record(row) for row in rows]

    async def mark_published(self, event_id: str, *, published_at: datetime) -> None:
        await self._update(
            event_id,
            status=OutboxStatus.PUBLISHED,
            published_at=published_at,
            locked_until=None,
            error=None,
        )

    async def mark_failed(
        self,
        event_id: str,
        *,
        error: str,
        available_at: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": str(OutboxStatus.FAILED),
            "error": error,
            "attempts": OutboxEvent.attempts + 1,
            "locked_until": None,
        }
        if available_at is not None:
            values["available_at"] = available_at
            values["status"] = str(OutboxStatus.PENDING)
        async with self.sessionmaker() as session, session.begin():
            stmt = (
                update(OutboxEvent).where(OutboxEvent.id == event_id).values(**values)
            )
            result = await session.execute(stmt)
            if getattr(result, "rowcount", 0) == 0:
                raise KeyError(event_id)

    async def delete_published_before(self, before: datetime, *, limit: int) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        old = (
            select(OutboxEvent.id)
            .where(
                OutboxEvent.status == str(OutboxStatus.PUBLISHED),
                OutboxEvent.published_at < before,
            )
            .limit(limit)
        )
        async with self.sessionmaker() as session, session.begin():
            result = await session.execute(
                delete(OutboxEvent).where(OutboxEvent.id.in_(old))
            )
            return int(getattr(result, "rowcount", 0) or 0)

    async def close(self) -> None:
        return None

    async def _update(self, event_id: str, **values: Any) -> None:
        async with self.sessionmaker() as session, session.begin():
            stmt = (
                update(OutboxEvent).where(OutboxEvent.id == event_id).values(**values)
            )
            result = await session.execute(stmt)
            if getattr(result, "rowcount", 0) == 0:
                raise KeyError(event_id)


def _to_record(event: OutboxEvent) -> OutboxRecord:
    return OutboxRecord(
        id=event.id,
        event_type=event.event_type,
        payload=event.payload,
        metadata=event.event_metadata,
        status=OutboxStatus(event.status),
        attempts=event.attempts,
        available_at=event.available_at,
        locked_until=event.locked_until,
        published_at=event.published_at,
        error=event.error,
    )


def new_outbox_row(
    *,
    event_type: str,
    payload: Mapping[str, Any],
    metadata: Mapping[str, Any] | None = None,
    available_at: datetime | None = None,
) -> OutboxEvent:
    """Build a pending row; lets a caller insert it in its own transaction."""
    return OutboxEvent(
        event_type=event_type,
        payload=dict(payload),
        event_metadata=dict(metadata or {}),
        status=str(OutboxStatus.PENDING),
        available_at=available_at or datetime.now(UTC),
    )


def _pending_stmt(*, limit: int, now: datetime, event_type_prefix: str | None = None):
    stmt = select(OutboxEvent).where(
        OutboxEvent.status == str(OutboxStatus.PENDING),
        OutboxEvent.available_at <= now,
        or_(
            OutboxEvent.locked_until.is_(None),
            OutboxEvent.locked_until <= now,
        ),
    )
    if event_type_prefix is not None:
        stmt = stmt.where(OutboxEvent.event_type.startswith(event_type_prefix))
    return stmt.order_by(OutboxEvent.available_at, OutboxEvent.created_at).limit(limit)
