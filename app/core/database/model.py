from datetime import UTC, datetime
from typing import Annotated

from sqlalchemy import DateTime
from sqlalchemy.orm import Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


id_key = Annotated[
    int,
    mapped_column(
        primary_key=True,
        index=True,
        autoincrement=True,
        sort_order=-999,
    ),
]


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        sort_order=998,
    )


class UpdatedAtMixin:
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utcnow,
        onupdate=utcnow,
        sort_order=999,
    )


class TimestampMixin(CreatedAtMixin, UpdatedAtMixin):
    pass


class ActorAuditMixin:
    created_by: Mapped[str | None] = mapped_column(
        nullable=True,
        default=None,
        sort_order=997,
    )
    updated_by: Mapped[str | None] = mapped_column(
        nullable=True,
        default=None,
        sort_order=997,
    )
