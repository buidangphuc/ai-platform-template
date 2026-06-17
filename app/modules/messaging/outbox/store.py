from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable


class OutboxStatus(StrEnum):
    PENDING = "pending"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass(frozen=True)
class OutboxRecord:
    id: str
    event_type: str
    payload: dict[str, Any]
    metadata: dict[str, Any] = field(default_factory=dict)
    status: OutboxStatus = OutboxStatus.PENDING
    attempts: int = 0
    available_at: datetime | None = None
    locked_until: datetime | None = None
    published_at: datetime | None = None
    error: str | None = None


@runtime_checkable
class OutboxStore(Protocol):
    async def enqueue(
        self,
        *,
        event_type: str,
        payload: Mapping[str, Any],
        metadata: Mapping[str, Any] | None = None,
        available_at: datetime | None = None,
    ) -> OutboxRecord: ...

    async def list_pending(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> Sequence[OutboxRecord]: ...

    async def claim_pending(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
        lock_seconds: float = 60.0,
    ) -> Sequence[OutboxRecord]: ...

    async def mark_published(
        self, event_id: str, *, published_at: datetime
    ) -> None: ...

    async def mark_failed(
        self,
        event_id: str,
        *,
        error: str,
        available_at: datetime | None = None,
    ) -> None: ...

    async def close(self) -> None: ...
