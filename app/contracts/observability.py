from collections.abc import Mapping
from datetime import datetime
from typing import AsyncContextManager, Protocol, runtime_checkable

from pydantic import BaseModel, Field


class TraceRecord(BaseModel):
    name: str
    attributes: dict[str, object] = Field(default_factory=dict)
    started_at: datetime
    ended_at: datetime


@runtime_checkable
class SpanHandle(Protocol):
    def set_attribute(self, key: str, value: object) -> None:
        raise NotImplementedError


@runtime_checkable
class ObservabilityClient(Protocol):
    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> AsyncContextManager[SpanHandle]:
        raise NotImplementedError

    async def record_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        raise NotImplementedError
