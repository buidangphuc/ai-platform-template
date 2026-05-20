from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class JobRequest(BaseModel):
    name: str
    payload: dict[str, object] = Field(default_factory=dict)
    queue: str = "default"
    metadata: dict[str, str] = Field(default_factory=dict)


class JobTicket(BaseModel):
    job_id: str
    status: JobStatus


class JobRecord(BaseModel):
    job_id: str
    name: str
    payload: dict[str, object]
    queue: str
    status: JobStatus
    result: dict[str, object] | None = None
    error: str | None = None


JobHandler = Callable[
    [dict[str, object]], Awaitable[dict[str, object] | None] | dict[str, object] | None
]


@runtime_checkable
class JobQueue(Protocol):
    def register_handler(self, name: str, handler: JobHandler) -> None:
        raise NotImplementedError

    async def enqueue(self, request: JobRequest) -> JobTicket:
        raise NotImplementedError

    async def get_status(self, job_id: str) -> JobRecord:
        raise NotImplementedError
