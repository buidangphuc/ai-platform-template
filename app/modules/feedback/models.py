from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[str] = mapped_column(
        String(64), primary_key=True, default=lambda: f"fb_{uuid4().hex}"
    )
    request_id: Mapped[str] = mapped_column(String(255), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(255), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    rating: Mapped[str] = mapped_column(String(32), nullable=False)
    labels: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
