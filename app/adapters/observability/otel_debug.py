import json
import logging
from collections.abc import Mapping
from typing import Any

from app.adapters.observability.debug import DebugObservability, DebugSpan
from app.contracts.observability import TraceRecord


class OTelDebugSpan(DebugSpan):
    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: Any,
    ) -> None:
        await super().__aexit__(exc_type, exc, traceback)
        self.sink.emit_record(kind="otel.trace", record=self.sink.finished_spans[-1])


class OTelDebugObservability(DebugObservability):
    def __init__(
        self,
        *,
        endpoint: str,
        logger: logging.Logger | None = None,
    ) -> None:
        super().__init__()
        self.endpoint = endpoint
        self.logger = logger or logging.getLogger("otel.debug")

    def start_span(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> OTelDebugSpan:
        return OTelDebugSpan(name=name, attributes=attributes, sink=self)

    async def record_event(
        self,
        name: str,
        *,
        attributes: Mapping[str, object] | None = None,
    ) -> None:
        await super().record_event(name, attributes=attributes)
        self.emit_record(kind="otel.event", record=self.events[-1])

    def emit_record(self, *, kind: str, record: TraceRecord) -> None:
        self.logger.info(
            "%s %s",
            kind,
            json.dumps(
                {
                    "endpoint": self.endpoint,
                    "name": record.name,
                    "attributes": record.attributes,
                    "started_at": record.started_at.isoformat(),
                    "ended_at": record.ended_at.isoformat(),
                },
                sort_keys=True,
            ),
        )
