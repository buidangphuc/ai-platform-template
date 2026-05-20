from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.contracts.observability import TraceRecord


class DebugSpan:
    def __init__(
        self,
        *,
        name: str,
        attributes: Mapping[str, object] | None,
        sink: "DebugObservability",
    ) -> None:
        self.name = name
        self.attributes = dict(attributes or {})
        self.sink = sink
        self.started_at = datetime.now(UTC)

    async def __aenter__(self) -> "DebugSpan":
        self.started_at = datetime.now(UTC)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        if exc is not None:
            self.attributes["error"] = str(exc)
        self.sink.finished_spans.append(
            TraceRecord(
                name=self.name,
                attributes=dict(self.attributes),
                started_at=self.started_at,
                ended_at=datetime.now(UTC),
            ),
        )

    def set_attribute(self, key: str, value: object) -> None:
        self.attributes[key] = value


class DebugObservability:
    def __init__(self) -> None:
        self.finished_spans: list[TraceRecord] = []
        self.events: list[TraceRecord] = []

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> DebugSpan:
        return DebugSpan(name=name, attributes=attributes, sink=self)

    async def record_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        self.events.append(
            TraceRecord(
                name=name,
                attributes=dict(attributes or {}),
                started_at=now,
                ended_at=now,
            ),
        )
