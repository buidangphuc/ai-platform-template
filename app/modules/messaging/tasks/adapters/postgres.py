"""Postgres-backed TaskStore using the project's async SQLAlchemy session."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.messaging.tasks.models import Task, TaskStatus
from app.modules.messaging.tasks.store import TaskRecord


class PostgresTaskStore:
    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self.sessionmaker = sessionmaker

    async def create(self, task: TaskRecord) -> None:
        async with self.sessionmaker() as session, session.begin():
            session.add(
                Task(
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
            )

    async def get(self, task_id: str) -> TaskRecord | None:
        async with self.sessionmaker() as session:
            row = await session.get(Task, task_id)
            return _to_record(row) if row else None

    async def mark_processing(self, task_id: str, *, lease_seconds: int) -> None:
        if lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive")
        locked_until = datetime.now(UTC) + timedelta(seconds=lease_seconds)
        await self._update(
            task_id,
            status=TaskStatus.PROCESSING,
            locked_until=locked_until,
            increment_attempts=True,
        )

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

    async def reclaim_stale_processing(self, *, now: datetime, limit: int = 100) -> int:
        if limit <= 0:
            raise ValueError("limit must be positive")
        async with self.sessionmaker() as session, session.begin():
            stmt = (
                update(Task)
                .where(
                    Task.status == str(TaskStatus.PROCESSING),
                    Task.locked_until.is_not(None),
                    Task.locked_until <= now,
                )
                .values(status=str(TaskStatus.QUEUED), locked_until=None)
                .execution_options(synchronize_session=False)
            )
            result = await session.execute(stmt)
            return int(getattr(result, "rowcount", 0) or 0)

    async def delete_expired(self, before: datetime) -> int:
        async with self.sessionmaker() as session, session.begin():
            stmt = delete(Task).where(Task.expires_at <= before)
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
        increment_attempts: bool = False,
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
        if increment_attempts:
            values["attempts"] = Task.attempts + 1

        async with self.sessionmaker() as session, session.begin():
            stmt = update(Task).where(Task.id == task_id).values(**values)
            outcome = await session.execute(stmt)
            if getattr(outcome, "rowcount", 0) == 0:
                raise KeyError(task_id)


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
