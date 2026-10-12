"""Backend-agnostic Task persistence contract.

Each adapter (memory / postgres / redis) implements the same surface so the
service layer and worker can swap durability without touching call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from app.modules.messaging.tasks.models import TaskStatus


@dataclass
class TaskRecord:
    id: str
    type: str
    status: TaskStatus
    payload: dict[str, Any]
    expires_at: datetime
    attempts: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    locked_until: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskRef:
    """Just enough of a task to announce it to a worker again."""

    id: str
    type: str


class TaskStore(Protocol):
    async def create(self, task: TaskRecord) -> None: ...

    async def get(self, task_id: str) -> TaskRecord | None: ...

    async def mark_processing(
        self,
        task_id: str,
        *,
        lease_seconds: int,
        now: datetime | None = None,
    ) -> bool:
        """Compare-and-set claim: QUEUED -> PROCESSING.

        Also takes over a PROCESSING task whose lease expired. Returns ``False``
        (changing nothing) for a live lease or a COMPLETED/FAILED task, so a
        redelivered message cannot run a task twice. Unknown id raises
        ``KeyError``.
        """
        ...

    async def mark_completed(self, task_id: str, result: dict[str, Any]) -> None: ...

    async def mark_failed(self, task_id: str, error: str) -> None: ...

    async def reclaim_stale_processing(
        self, *, now: datetime, limit: int = 100
    ) -> list[TaskRef]:
        """Reset up to ``limit`` PROCESSING tasks whose lease expired to QUEUED.

        Returns the reclaimed tasks so the caller can dispatch them again.
        """
        ...

    async def delete_expired(self, before: datetime) -> int: ...

    async def close(self) -> None: ...
