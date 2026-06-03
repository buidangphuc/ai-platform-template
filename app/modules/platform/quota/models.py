from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import uuid4


class QuotaReservationStatus(StrEnum):
    RESERVED = "reserved"
    FINALIZED = "finalized"
    REFUNDED = "refunded"


@dataclass(frozen=True)
class QuotaPolicy:
    resource: str
    limit: int
    window_seconds: int
    default_cost: int = 1

    def __post_init__(self) -> None:
        if not self.resource:
            raise ValueError("resource must be non-empty")
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.window_seconds <= 0:
            raise ValueError("window_seconds must be positive")
        if self.default_cost <= 0:
            raise ValueError("default_cost must be positive")


@dataclass(frozen=True)
class QuotaWindow:
    key: str
    reset_at: datetime


@dataclass(frozen=True)
class QuotaUsage:
    subject_id: str
    resource: str
    window_key: str
    used: int
    limit: int
    remaining: int
    reset_at: datetime


@dataclass(frozen=True)
class QuotaReservation:
    id: str
    subject_id: str
    resource: str
    window_key: str
    cost: int
    status: QuotaReservationStatus
    usage: QuotaUsage
    idempotency_key: str | None = None


@dataclass(frozen=True)
class ReserveQuota:
    subject_id: str
    resource: str
    window_key: str
    limit: int
    cost: int
    reset_at: datetime
    reservation_id: str
    idempotency_key: str | None = None

    @classmethod
    def create(
        cls,
        *,
        subject_id: str,
        resource: str,
        window_key: str,
        limit: int,
        cost: int,
        reset_at: datetime,
        idempotency_key: str | None = None,
    ) -> ReserveQuota:
        return cls(
            subject_id=subject_id,
            resource=resource,
            window_key=window_key,
            limit=limit,
            cost=cost,
            reset_at=reset_at,
            reservation_id=str(uuid4()),
            idempotency_key=idempotency_key,
        )

    def __post_init__(self) -> None:
        if not self.subject_id:
            raise ValueError("subject_id must be non-empty")
        if not self.resource:
            raise ValueError("resource must be non-empty")
        if not self.window_key:
            raise ValueError("window_key must be non-empty")
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if self.cost <= 0:
            raise ValueError("cost must be positive")


@dataclass(frozen=True)
class QuotaUsageQuery:
    subject_id: str
    resource: str
    window_key: str
    limit: int
    reset_at: datetime
