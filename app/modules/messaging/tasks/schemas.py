from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.modules.messaging.tasks.models import TaskStatus


class SchemaBase(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
        use_enum_values=True,
        str_strip_whitespace=True,
    )


class TaskSubmitResponse(SchemaBase):
    task_id: str
    status: TaskStatus
    expires_at: datetime


class TaskResponse(SchemaBase):
    task_id: str = Field(alias="id")
    type: str
    status: TaskStatus
    payload: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None
    attempts: int
    created_at: datetime | None = None
    updated_at: datetime | None = None
    expires_at: datetime
