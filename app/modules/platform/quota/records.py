from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.modules.platform.quota.models import QuotaReservationStatus


class QuotaCounter(Base, TimestampMixin):
    __tablename__ = "quota_counters"
    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "resource",
            "window_key",
            name="uq_quota_counters_subject_resource_window",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    window_key: Mapped[str] = mapped_column(String(64), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    limit: Mapped[int] = mapped_column("quota_limit", Integer, nullable=False)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QuotaReservationRecord(Base, TimestampMixin):
    __tablename__ = "quota_reservations"
    __table_args__ = (
        UniqueConstraint(
            "subject_id",
            "resource",
            "window_key",
            "idempotency_key",
            name="uq_quota_reservations_idempotency",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    resource: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    window_key: Mapped[str] = mapped_column(String(64), nullable=False)
    cost: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=QuotaReservationStatus.RESERVED.value,
        index=True,
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reset_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
