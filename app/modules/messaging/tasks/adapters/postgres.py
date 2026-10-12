"""Postgres-backed TaskStore using the project's async SQLAlchemy session."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, delete, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.messaging.tasks.models import Task, TaskStatus
from app.modules.messaging.tasks.store import (
    MAX_ATTEMPTS_EXCEEDED,
    TaskRecord,
    TaskRef,
)


class PostgresTaskStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def create(self, task: TaskRecord) -> None:
        async with self.sessionmaker() as session, session.begin():
            session.add(new_task_row(task))

    async def get(self, task_id: str) -> TaskRecord | None:
        async with self.sessionmaker() as session:
            row = await session.get(Task, task_id)
            return _to_record(row) if row else None

    async def mark_processing(
        self,
        task_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        now = now or datetime.now(UTC)
        stmt = (
            update(Task)
            .where(
                Task.id == task_id,
                or_(
                    Task.status == str(TaskStatus.QUEUED),
                    and_(
                        Task.status == str(TaskStatus.PROCESSING),
                        Task.locked_until <= now,
                    ),
                ),
            )
            .values(
                status=str(TaskStatus.PROCESSING),
                locked_until=now + timedelta(seconds=lease_seconds),
                attempts=Task.attempts + 1,
            )
            .execution_options(synchronize_session=False)
        )
        async with self.sessionmaker() as session, session.begin():
            claimed = int(getattr(await session.execute(stmt), "rowcount", 0) or 0)
            if claimed:
                return True
            if await session.scalar(select(Task.id).where(Task.id == task_id)) is None:
                raise KeyError(task_id)
            return False

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self._update(
            task_id,
            status=TaskStatus.COMPLETED,
            result=result,
            locked_until=None,
        )

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self._update(
            task_id, status=TaskStatus.FAILED, error=error, locked_until=None
        )

    async def reclaim_stale_processing(
        self, *, now: datetime, limit: int = 100, max_attempts: int
    ) -> list[TaskRef]:
        async with self.sessionmaker() as session, session.begin():
            return await reclaim_stale_in(
                session, now=now, limit=limit, max_attempts=max_attempts
            )

    async def delete_expired(self, before: datetime, *, limit: int) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        expired = select(Task.id).where(Task.expires_at <= before).limit(limit)
        async with self.sessionmaker() as session, session.begin():
            stmt = delete(Task).where(Task.id.in_(expired))
            result = await session.execute(stmt)
            return int(getattr(result, "rowcount", 0) or 0)

    async def close(self) -> None:
        return None

    async def _update(
        self,
        task_id: str,
        *,
        status: TaskStatus,
        result: dict[str, Any] | None = None,
        error: str | None = None,
        locked_until: datetime | None = None,
    ) -> None:
        values: dict[str, Any] = {
            "status": str(status),
            "locked_until": locked_until,
        }
        if result is not None:
            values["result"] = result
        if error is not None:
            values["error"] = error

        async with self.sessionmaker() as session, session.begin():
            stmt = update(Task).where(Task.id == task_id).values(**values)
            outcome = await session.execute(stmt)
            if getattr(outcome, "rowcount", 0) == 0:
                raise KeyError(task_id)


def new_task_row(task: TaskRecord) -> Task:
    return Task(
        id=task.id,
        type=task.type,
        status=str(task.status),
        payload=task.payload,
        result=task.result,
        error=task.error,
        attempts=task.attempts,
        locked_until=task.locked_until,
        expires_at=task.expires_at,
    )


async def reclaim_stale_in(
    session: AsyncSession, *, now: datetime, limit: int, max_attempts: int
) -> list[TaskRef]:
    """Settle up to ``limit`` expired-lease tasks inside the caller's transaction.

    Tasks already claimed ``max_attempts`` times become FAILED in the same
    statement; only the requeued ones are returned (and need announcing).

    The bounded sub-select with ``SKIP LOCKED`` keeps concurrent reclaimers from
    contending on (or double-claiming) the same rows.
    """
    if limit <= 0:
        raise ValueError("limit must be positive")
    stale = (
        select(Task.id)
        .where(
            Task.status == str(TaskStatus.PROCESSING),
            Task.locked_until.is_not(None),
            Task.locked_until <= now,
        )
        .order_by(Task.locked_until)
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    exhausted = Task.attempts >= max_attempts
    stmt = (
        update(Task)
        .where(Task.id.in_(stale))
        .values(
            status=case(
                (exhausted, str(TaskStatus.FAILED)), else_=str(TaskStatus.QUEUED)
            ),
            error=case((exhausted, MAX_ATTEMPTS_EXCEEDED), else_=Task.error),
            locked_until=None,
        )
        .returning(Task.id, Task.type, Task.status)
        .execution_options(synchronize_session=False)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TaskRef(id=row.id, type=row.type)
        for row in rows
        if row.status == str(TaskStatus.QUEUED)
    ]


def _to_record(task: Task) -> TaskRecord:
    return TaskRecord(
        id=task.id,
        type=task.type,
        status=TaskStatus(task.status),
        payload=task.payload,
        result=task.result,
        error=task.error,
        attempts=task.attempts,
        locked_until=task.locked_until,
        expires_at=task.expires_at,
        created_at=task.created_at.astimezone(UTC) if task.created_at else None,
        updated_at=task.updated_at.astimezone(UTC) if task.updated_at else None,
    )
