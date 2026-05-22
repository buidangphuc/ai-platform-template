from datetime import UTC, datetime, timedelta

import pytest
from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.resilience import RetryPolicy
from app.modules.outbox.factory import OutboxAddon, build_outbox_store
from app.modules.outbox.models import OutboxEvent
from app.modules.outbox.publisher import (
    OutboxPublisher,
    QueueOutboxSink,
    WebhookOutboxSink,
)
from app.modules.outbox.store import OutboxRecord, OutboxStatus, OutboxStore
from app.modules.webhooks.dispatcher import WebhookDeliveryResult


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
    }
    base.update(overrides)
    return Settings(**base)


def test_outbox_record_is_generic_platform_shape():
    record = OutboxRecord(
        id="evt-1",
        event_type="generic.event",
        payload={"ok": True},
        metadata={"source": "test"},
        status=OutboxStatus.PENDING,
        attempts=0,
        available_at=datetime(2026, 5, 21, tzinfo=UTC),
    )

    assert record.event_type == "generic.event"
    assert record.payload == {"ok": True}
    assert record.metadata == {"source": "test"}


def test_outbox_model_uses_safe_metadata_column_name():
    assert OutboxEvent.__tablename__ == "outbox_events"
    assert OutboxEvent.event_metadata.property.columns[0].name == "metadata"


def test_build_outbox_store_requires_sessionmaker_for_postgres():
    with pytest.raises(RuntimeError, match="sessionmaker"):
        build_outbox_store(_settings(OUTBOX_ENABLED=True))


def test_build_outbox_store_returns_protocol_implementation():
    store = build_outbox_store(_settings(OUTBOX_ENABLED=True), sessionmaker=object())

    assert isinstance(store, OutboxStore)


async def test_outbox_addon_attaches_store_when_enabled():
    app = FastAPI()
    addon = OutboxAddon()

    await addon.open(
        app,
        ApplicationResources(sessionmaker=object()),
        _settings(OUTBOX_ENABLED=True),
    )

    assert isinstance(app.state.outbox_store, OutboxStore)


def test_outbox_addon_respects_enabled_flag():
    addon = OutboxAddon()

    assert addon.is_enabled(_settings(OUTBOX_ENABLED=True)) is True
    assert addon.is_enabled(_settings(OUTBOX_ENABLED=False)) is False


class _FakeOutboxStore:
    def __init__(self, records: list[OutboxRecord]) -> None:
        self.records = records
        self.published: list[tuple[str, datetime]] = []
        self.failed: list[tuple[str, str, datetime | None]] = []
        self.claim_calls: list[tuple[int, datetime | None, float]] = []
        self.list_calls = 0

    async def list_pending(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[OutboxRecord]:
        self.list_calls += 1
        return self.records[:limit]

    async def claim_pending(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
        lock_seconds: float = 60.0,
    ) -> list[OutboxRecord]:
        self.claim_calls.append((limit, now, lock_seconds))
        return self.records[:limit]

    async def mark_published(self, event_id: str, *, published_at: datetime) -> None:
        self.published.append((event_id, published_at))

    async def mark_failed(
        self,
        event_id: str,
        *,
        error: str,
        available_at: datetime | None = None,
    ) -> None:
        self.failed.append((event_id, error, available_at))


class _FakeQueue:
    def __init__(self) -> None:
        self.payloads: list[dict[str, object]] = []

    async def send(self, payload: dict[str, object]) -> str:
        self.payloads.append(payload)
        return "msg-1"


def _record(**overrides: object) -> OutboxRecord:
    values: dict[str, object] = {
        "id": "evt-1",
        "event_type": "generic.event",
        "payload": {"value": 1},
        "metadata": {"trace_id": "trace-1"},
        "attempts": 0,
        "available_at": datetime(2026, 5, 22, tzinfo=UTC),
    }
    values.update(overrides)
    return OutboxRecord(**values)


async def test_outbox_publisher_sends_generic_queue_payload_and_marks_published():
    now = datetime(2026, 5, 22, 10, 30, tzinfo=UTC)
    store = _FakeOutboxStore([_record()])
    queue = _FakeQueue()
    publisher = OutboxPublisher(store=store, sink=QueueOutboxSink(queue))

    report = await publisher.publish_pending(now=now)

    assert queue.payloads == [
        {
            "id": "evt-1",
            "type": "generic.event",
            "payload": {"value": 1},
            "metadata": {"trace_id": "trace-1"},
        }
    ]
    assert store.published == [("evt-1", now)]
    assert report.total == 1
    assert report.published == 1
    assert report.failed == 0
    assert report.retried == 0
    assert store.claim_calls == [(100, now, 60.0)]
    assert store.list_calls == 0


async def test_outbox_publisher_accepts_custom_claim_lock_seconds():
    now = datetime(2026, 5, 22, 10, 30, tzinfo=UTC)
    store = _FakeOutboxStore([_record()])
    queue = _FakeQueue()
    publisher = OutboxPublisher(store=store, sink=QueueOutboxSink(queue))

    await publisher.publish_pending(now=now, limit=5, lock_seconds=15.5)

    assert store.claim_calls == [(5, now, 15.5)]


async def test_outbox_publisher_rejects_non_positive_claim_lock_seconds():
    publisher = OutboxPublisher(
        store=_FakeOutboxStore([]),
        sink=QueueOutboxSink(_FakeQueue()),
    )

    with pytest.raises(ValueError, match="lock_seconds must be positive"):
        await publisher.publish_pending(lock_seconds=0)


async def test_outbox_publisher_reschedules_transient_failures_before_max_attempts():
    class _FailingSink:
        async def publish(
            self,
            record: OutboxRecord,
            *,
            now: datetime,
        ) -> None:
            raise RuntimeError("queue unavailable")

    now = datetime(2026, 5, 22, 10, 30, tzinfo=UTC)
    store = _FakeOutboxStore([_record(attempts=0)])
    publisher = OutboxPublisher(
        store=store,
        sink=_FailingSink(),
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=(5.0,)),
    )

    report = await publisher.publish_pending(now=now)

    assert store.published == []
    assert store.failed == [("evt-1", "queue unavailable", now + timedelta(seconds=5))]
    assert report.retried == 1
    assert report.failed == 0


async def test_outbox_publisher_marks_final_failure_after_max_attempts():
    class _FailingSink:
        async def publish(
            self,
            record: OutboxRecord,
            *,
            now: datetime,
        ) -> None:
            raise RuntimeError("webhook rejected")

    now = datetime(2026, 5, 22, 10, 30, tzinfo=UTC)
    store = _FakeOutboxStore([_record(attempts=2)])
    publisher = OutboxPublisher(
        store=store,
        sink=_FailingSink(),
        retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=(5.0,)),
    )

    report = await publisher.publish_pending(now=now)

    assert store.failed == [("evt-1", "webhook rejected", None)]
    assert report.failed == 1
    assert report.retried == 0


async def test_webhook_outbox_sink_dispatches_generic_envelope():
    class _Dispatcher:
        def __init__(self) -> None:
            self.calls: list[tuple[str, object]] = []

        async def dispatch(self, url: str, envelope: object) -> WebhookDeliveryResult:
            self.calls.append((url, envelope))
            return WebhookDeliveryResult(status_code=202)

    now = datetime(2026, 5, 22, 10, 30, tzinfo=UTC)
    dispatcher = _Dispatcher()
    sink = WebhookOutboxSink(
        url="https://example.test/webhooks",
        dispatcher=dispatcher,
    )

    await sink.publish(_record(), now=now)

    url, envelope = dispatcher.calls[0]
    assert url == "https://example.test/webhooks"
    assert envelope.id == "evt-1"
    assert envelope.type == "generic.event"
    assert envelope.occurred_at == now
