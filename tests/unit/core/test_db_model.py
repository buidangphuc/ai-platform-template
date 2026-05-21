from datetime import UTC, datetime

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.db_model import (
    ActorAuditMixin,
    CreatedAtMixin,
    TimestampMixin,
    UpdatedAtMixin,
    utcnow,
)


def test_utcnow_returns_timezone_aware_datetime():
    now = utcnow()
    assert isinstance(now, datetime)
    assert now.tzinfo == UTC


def test_created_at_mixin_declares_column():
    class _CreatedOnly(Base, CreatedAtMixin):
        __tablename__ = "_test_created_only"
        id: Mapped[str] = mapped_column(String(36), primary_key=True)

    assert "created_at" in _CreatedOnly.__table__.columns
    column = _CreatedOnly.__table__.columns["created_at"]
    assert column.nullable is False


def test_timestamp_mixin_declares_both_columns():
    class _Both(Base, TimestampMixin):
        __tablename__ = "_test_both"
        id: Mapped[str] = mapped_column(String(36), primary_key=True)

    assert "created_at" in _Both.__table__.columns
    assert "updated_at" in _Both.__table__.columns


def test_actor_audit_mixin_declares_nullable_columns():
    class _Audited(Base, ActorAuditMixin, UpdatedAtMixin):
        __tablename__ = "_test_audited"
        id: Mapped[str] = mapped_column(String(36), primary_key=True)

    created_by = _Audited.__table__.columns["created_by"]
    updated_by = _Audited.__table__.columns["updated_by"]
    assert created_by.nullable is True
    assert updated_by.nullable is True
