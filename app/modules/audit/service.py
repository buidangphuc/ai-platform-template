from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any

from app.core.context import ServiceContext
from app.modules.audit.models import AuditEvent

FORBIDDEN_AUDIT_METADATA_KEYS = frozenset(
    {
        "answer",
        "completion",
        "content",
        "input",
        "message",
        "messages",
        "output",
        "payload",
        "prompt",
        "question",
        "raw_payload",
        "response",
        "text",
        "user_input",
    }
)


def validate_audit_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    _reject_raw_content_keys(metadata)
    return dict(metadata)


async def record_audit_event(
    context: ServiceContext,
    *,
    event_type: str,
    resource_type: str | None = None,
    resource_id: str | None = None,
    status: str,
    duration_ms: int | None = None,
    error_code: str | None = None,
    langfuse_trace_id: str | None = None,
    metadata: Mapping[str, Any] | None = None,
    pii_scrubbed: bool = True,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> AuditEvent:
    event = AuditEvent(
        event_type=event_type,
        actor_id=context.principal.id,
        actor_type=context.principal.type,
        request_id=context.request_id,
        resource_type=resource_type,
        resource_id=resource_id,
        status=status,
        duration_ms=duration_ms,
        error_code=error_code,
        langfuse_trace_id=langfuse_trace_id,
        event_metadata=validate_audit_metadata(metadata or {}),
        pii_scrubbed=pii_scrubbed,
        created_at=now(),
    )
    context.db.add(event)
    return event


def _reject_raw_content_keys(value: Any, *, path: str = "") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized_key = str(key).lower()
            child_path = f"{path}.{key}" if path else str(key)
            if normalized_key in FORBIDDEN_AUDIT_METADATA_KEYS:
                raise ValueError(
                    f"Audit metadata key {child_path!r} may contain raw content"
                )
            _reject_raw_content_keys(child, path=child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_raw_content_keys(child, path=f"{path}[{index}]")
