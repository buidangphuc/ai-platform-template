from datetime import UTC, datetime

import pytest

from app.modules.audit.models import AuditEvent
from app.modules.audit.service import record_audit_event, validate_audit_metadata
from app.modules.identity.schemas import Principal


class _FakeSession:
    def __init__(self) -> None:
        self.added = []

    def add(self, value):
        self.added.append(value)


class _Context:
    request_id = "req-1"
    principal = Principal(id="svc-local", type="service", scopes=("admin",))
    db = _FakeSession()


def test_audit_event_model_uses_safe_metadata_column_name():
    assert AuditEvent.__tablename__ == "audit_events"
    assert AuditEvent.event_metadata.property.columns[0].name == "metadata"


def test_validate_audit_metadata_rejects_raw_ai_content_keys():
    with pytest.raises(ValueError, match="prompt"):
        validate_audit_metadata({"prompt": "raw user text"})

    with pytest.raises(ValueError, match="messages"):
        validate_audit_metadata({"nested": {"messages": ["raw"]}})


async def test_record_audit_event_uses_service_context_and_safe_metadata():
    context = _Context()

    event = await record_audit_event(
        context,
        event_type="document.indexed",
        resource_type="document",
        resource_id="doc-1",
        status="succeeded",
        duration_ms=42,
        error_code=None,
        langfuse_trace_id="trace-1",
        metadata={"chunk_count": 3, "source_id": "upload-1"},
        pii_scrubbed=True,
        now=lambda: datetime(2026, 5, 21, tzinfo=UTC),
    )

    assert context.db.added == [event]
    assert event.actor_id == "svc-local"
    assert event.actor_type == "service"
    assert event.request_id == "req-1"
    assert event.event_type == "document.indexed"
    assert event.resource_type == "document"
    assert event.resource_id == "doc-1"
    assert event.status == "succeeded"
    assert event.duration_ms == 42
    assert event.langfuse_trace_id == "trace-1"
    assert event.event_metadata == {"chunk_count": 3, "source_id": "upload-1"}
    assert event.pii_scrubbed is True
