"""Postgres-backed TaskStore using the project's async SQLAlchemy session."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.modules.tasks.models import Task, TaskStatus
from app.modules.tasks.store import TaskRecord


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

    async def mark_processing(self, task_id: str) -> None:
        await self._update(
            task_id,
            status=TaskStatus.PROCESSING,
            increment_attempts=True,
        )

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None:
        await self._update(task_id, status=TaskStatus.COMPLETED, result=result)

    async def mark_failed(self, task_id: str, error: str) -> None:
        await self._update(task_id, status=TaskStatus.FAILED, error=error)

    async def delete_expired(self, before: datetime) -> int:
        async with self.sessionmaker() as session, session.begin():
            stmt = delete(Task).where(Task.expires_at <= before)
            result = await session.execute(stmt)
            return result.rowcount or 0

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
    ) -> None:
        values: dict[str, Any] = {"status": str(status)}
        if result is not None:
            values["result"] = result
        if error is not None:
            values["error"] = error
        if increment_attempts:
            values["attempts"] = Task.attempts + 1

        async with self.sessionmaker() as session, session.begin():
            stmt = update(Task).where(Task.id == task_id).values(**values)
            outcome = await session.execute(stmt)
            if outcome.rowcount == 0:
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
