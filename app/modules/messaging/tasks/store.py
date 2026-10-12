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
    # Authenticated subject that submitted the task. "" only for rows created
    # before ownership existed (no principal matches it, so the API never serves them).
    principal_id: str = ""
    # Id of the HTTP request that submitted the task; reclaim re-announces with it
    # so worker logs of a retry still correlate. ``None`` when unknown.
    request_id: str | None = None


# Stored as ``TaskRecord.error`` when reclaim gives up on a task that keeps
# losing its lease (a worker crash every time). A code, never exception text.
MAX_ATTEMPTS_EXCEEDED = "max_attempts_exceeded"


@dataclass(frozen=True)
class TaskRef:
    """Just enough of a task to announce it to a worker again."""

    id: str
    type: str
    request_id: str | None = None


class TaskStore(Protocol):
    async def create(self, task: TaskRecord) -> None: ...

    async def get(
        self, task_id: str, *, principal_id: str | None = None
    ) -> TaskRecord | None:
        """Fetch a task; with ``principal_id`` only if that principal owns it.

        ``None`` (the worker's read) is owner-agnostic. A task owned by someone
        else is indistinguishable from a missing one.
        """
        ...

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
        self, *, now: datetime, limit: int = 100, max_attempts: int
    ) -> list[TaskRef]:
        """Settle up to ``limit`` PROCESSING tasks whose lease expired.

        A task that has already been claimed ``max_attempts`` times becomes
        FAILED with error ``MAX_ATTEMPTS_EXCEEDED`` (it keeps crashing its
        worker); every other one goes back to QUEUED. Returns only the requeued
        tasks, which the caller must announce again.
        """
        ...

    async def delete_expired(self, before: datetime, *, limit: int) -> int:
        """Delete up to ``limit`` tasks expired at ``before``; returns the count."""
        ...

    async def close(self) -> None: ...
