"""The one message contract between task dispatch and the worker.

Every dispatcher (direct queue send, outbox relay) publishes exactly
``TaskMessage.to_body()``; the worker parses exactly ``TaskMessage.from_body``.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.modules.messaging.queue.worker import NonRetryableMessageError


class TaskMessage(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    task_id: str = Field(min_length=1)
    type: str = Field(min_length=1)
    # Request id of the submitting HTTP request, so worker logs correlate with it.
    request_id: str | None = Field(default=None, min_length=1)

    def to_body(self) -> dict[str, Any]:
        return self.model_dump(exclude_none=True)

    @classmethod
    def from_body(cls, body: dict[str, Any]) -> TaskMessage:
        """Parse a queue body; a body that is not a task message never will be."""
        try:
            return cls.model_validate(body)
        except ValidationError as exc:
            raise NonRetryableMessageError(
                f"malformed task message: {exc.error_count()} invalid field(s)"
            ) from exc
