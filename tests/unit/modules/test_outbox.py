from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.bootstrap.addons.outbox import OutboxAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.resilience import RetryPolicy
from app.modules.messaging.outbox.adapters import PostgresOutboxStore
from app.modules.messaging.outbox.factory import build_outbox_store
from app.modules.messaging.outbox.models import OutboxEvent
from app.modules.messaging.outbox.publisher import (
    OutboxPublisher,
    QueueOutboxSink,
    WebhookOutboxSink,
)
from app.modules.messaging.outbox.store import OutboxRecord, OutboxStatus
from app.modules.messaging.queue.adapters.sqs import SQSQueueGateway
from app.modules.messaging.webhooks.dispatcher import HttpWebhookDispatcher
from app.modules.messaging.webhooks.signing import WebhookSigner
from tests.factories import build_test_settings, open_addon
from tests.http_server import LocalHttpServer, Reply
from tests.infra import SqsQueue

Sessions = async_sessionmaker[AsyncSession]

RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay_seconds=5.0,
    max_delay_seconds=5.0,
    rng=lambda: 1.0,
    retry_on=lambda _error: True,
)


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


@pytest.fixture()
async def queue(
    sqs_queue: SqsQueue, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[SQSQueueGateway]:
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    gateway = await SQSQueueGateway(
        queue_url=sqs_queue.url,
        region_name=sqs_queue.region,
        endpoint_url=sqs_queue.endpoint_url,
    ).open()
    try:
        yield gateway
    finally:
        await gateway.close()


@pytest.fixture()
async def http_client() -> AsyncIterator[httpx.AsyncClient]:
    async with httpx.AsyncClient() as client:
        yield client


def _webhook_sink(
    server: LocalHttpServer, client: httpx.AsyncClient
) -> WebhookOutboxSink:
    return WebhookOutboxSink(
        url=f"{server.url}/webhooks",
        dispatcher=HttpWebhookDispatcher(
            signer=WebhookSigner(secret="secret"), client=client
        ),
    )


async def _event(sessions: Sessions, event_id: str) -> OutboxEvent:
    async with sessions() as session:
        return (
            await session.scalars(select(OutboxEvent).where(OutboxEvent.id == event_id))
        ).one()


async def _enqueue(
    store: PostgresOutboxStore, event_type: str = "generic.event", **kwargs
) -> OutboxRecord:
    return await store.enqueue(
        event_type=event_type,
        payload={"value": 1},
        metadata={"trace_id": "trace-1"},
        available_at=datetime.now(UTC) - timedelta(seconds=1),
        **kwargs,
    )


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


def test_build_outbox_store_returns_postgres_store(pg_sessionmaker: Sessions):
    store = build_outbox_store(
        _settings(OUTBOX_ENABLED=True, DATABASE_ENABLED=True), pg_sessionmaker
    )

    assert isinstance(store, PostgresOutboxStore)


async def test_outbox_addon_attaches_store_when_enabled(pg_sessionmaker: Sessions):
    resources = ApplicationResources(sessionmaker=pg_sessionmaker)
    addon = OutboxAddon()

    stack = await open_addon(
        addon, resources, _settings(OUTBOX_ENABLED=True, DATABASE_ENABLED=True)
    )

    assert isinstance(resources.outbox_store, PostgresOutboxStore)
    record = await resources.outbox_store.enqueue(
        event_type="generic.event", payload={"ok": True}
    )
    assert (await _event(pg_sessionmaker, record.id)).status == "pending"
    await stack.aclose()


def test_outbox_addon_respects_enabled_flag():
    addon = OutboxAddon()

    assert addon.is_enabled(_settings(OUTBOX_ENABLED=True, DATABASE_ENABLED=True))
    assert addon.is_enabled(_settings(OUTBOX_ENABLED=False)) is False


async def test_store_enqueue_persists_a_pending_event(pg_sessionmaker: Sessions):
    store = PostgresOutboxStore(pg_sessionmaker)

    record = await _enqueue(store)

    assert record.status is OutboxStatus.PENDING
    assert record.attempts == 0
    row = await _event(pg_sessionmaker, record.id)
    assert row.event_type == "generic.event"
    assert row.payload == {"value": 1}
    assert row.event_metadata == {"trace_id": "trace-1"}


async def test_store_claim_locks_rows_for_the_requested_seconds(
    pg_sessionmaker: Sessions,
):
    store = PostgresOutboxStore(pg_sessionmaker)
    record = await _enqueue(store)
    now = datetime.now(UTC)

    [claimed] = await store.claim_pending(now=now, lock_seconds=15.5)

    assert claimed.id == record.id
    assert claimed.locked_until == now + timedelta(seconds=15.5)
    assert await store.claim_pending(now=now + timedelta(seconds=10)) == []
    [again] = await store.claim_pending(now=now + timedelta(seconds=16))
    assert again.id == record.id


async def test_store_claim_rejects_non_positive_arguments(pg_sessionmaker: Sessions):
    store = PostgresOutboxStore(pg_sessionmaker)

    with pytest.raises(ValueError, match="limit must be positive"):
        await store.claim_pending(limit=0)
    with pytest.raises(ValueError, match="lock_seconds must be positive"):
        await store.claim_pending(lock_seconds=0)


async def test_store_marks_on_unknown_events_raise_key_error(
    pg_sessionmaker: Sessions,
):
    store = PostgresOutboxStore(pg_sessionmaker)

    with pytest.raises(KeyError):
        await store.mark_published("missing", published_at=datetime.now(UTC))
    with pytest.raises(KeyError):
        await store.mark_failed("missing", error="boom")


async def test_store_deletes_only_old_published_events(pg_sessionmaker: Sessions):
    store = PostgresOutboxStore(pg_sessionmaker)
    now = datetime.now(UTC)
    old = await _enqueue(store)
    recent = await _enqueue(store)
    pending = await _enqueue(store)
    await store.mark_published(old.id, published_at=now - timedelta(days=2))
    await store.mark_published(recent.id, published_at=now)

    deleted = await store.delete_published_before(now - timedelta(days=1), limit=10)

    assert deleted == 1
    async with pg_sessionmaker() as session:
        ids = set(await session.scalars(select(OutboxEvent.id)))
    assert ids == {recent.id, pending.id}
    with pytest.raises(ValueError, match="limit must be positive"):
        await store.delete_published_before(now, limit=0)
    await store.close()


async def test_outbox_publisher_sends_generic_queue_payload_and_marks_published(
    pg_sessionmaker: Sessions, queue: SQSQueueGateway
):
    store = PostgresOutboxStore(pg_sessionmaker)
    record = await _enqueue(store)
    now = datetime.now(UTC)
    publisher = OutboxPublisher(store=store, sink=QueueOutboxSink(queue))

    report = await publisher.publish_pending(now=now)

    [message] = await queue.receive(max_messages=1, wait_seconds=2)
    assert message.body == {
        "id": record.id,
        "type": "generic.event",
        "payload": {"value": 1},
        "metadata": {"trace_id": "trace-1"},
    }
    row = await _event(pg_sessionmaker, record.id)
    assert row.status == "published"
    assert row.published_at == now
    assert row.locked_until is None
    assert (report.total, report.published, report.failed, report.retried) == (
        1,
        1,
        0,
        0,
    )


async def test_outbox_publisher_honours_the_batch_limit(
    pg_sessionmaker: Sessions, queue: SQSQueueGateway
):
    store = PostgresOutboxStore(pg_sessionmaker)
    for _ in range(3):
        await _enqueue(store)
    publisher = OutboxPublisher(store=store, sink=QueueOutboxSink(queue))

    first = await publisher.publish_pending(limit=2, lock_seconds=15.5)
    second = await publisher.publish_pending(limit=2)

    assert (first.total, second.total) == (2, 1)


async def test_outbox_publisher_rejects_non_positive_claim_lock_seconds(
    pg_sessionmaker: Sessions, queue: SQSQueueGateway
):
    publisher = OutboxPublisher(
        store=PostgresOutboxStore(pg_sessionmaker), sink=QueueOutboxSink(queue)
    )

    with pytest.raises(ValueError, match="lock_seconds must be positive"):
        await publisher.publish_pending(lock_seconds=0)


async def test_outbox_publisher_reschedules_transient_failures_before_max_attempts(
    pg_sessionmaker: Sessions,
    local_http_server: LocalHttpServer,
    http_client: httpx.AsyncClient,
):
    local_http_server.script("/webhooks", Reply(503))
    store = PostgresOutboxStore(pg_sessionmaker)
    record = await _enqueue(store)
    now = datetime.now(UTC)
    publisher = OutboxPublisher(
        store=store,
        sink=_webhook_sink(local_http_server, http_client),
        retry_policy=RETRY_POLICY,
    )

    report = await publisher.publish_pending(now=now)

    row = await _event(pg_sessionmaker, record.id)
    assert row.status == "pending"
    assert row.attempts == 1
    assert row.error == "HTTP 503"
    assert row.available_at == now + timedelta(seconds=5)
    assert row.locked_until is None
    assert (report.retried, report.failed, report.published) == (1, 0, 0)


async def test_outbox_publisher_marks_final_failure_after_max_attempts(
    pg_sessionmaker: Sessions,
    local_http_server: LocalHttpServer,
    http_client: httpx.AsyncClient,
):
    local_http_server.script("/webhooks", Reply(503))
    store = PostgresOutboxStore(pg_sessionmaker)
    record = await _enqueue(store)
    now = datetime.now(UTC)
    publisher = OutboxPublisher(
        store=store,
        sink=_webhook_sink(local_http_server, http_client),
        retry_policy=RETRY_POLICY,
    )

    reports = [
        await publisher.publish_pending(now=now + timedelta(seconds=10 * attempt))
        for attempt in range(3)
    ]

    assert [(r.retried, r.failed) for r in reports] == [(1, 0), (1, 0), (0, 1)]
    row = await _event(pg_sessionmaker, record.id)
    assert row.status == "failed"
    assert row.attempts == 3
    assert row.error == "HTTP 503"
    assert await store.claim_pending(now=now + timedelta(days=1)) == []


async def test_outbox_publisher_retries_when_the_webhook_endpoint_is_unreachable(
    pg_sessionmaker: Sessions,
    local_http_server: LocalHttpServer,
    http_client: httpx.AsyncClient,
):
    sink = _webhook_sink(local_http_server, http_client)
    await local_http_server.stop()
    store = PostgresOutboxStore(pg_sessionmaker)
    record = await _enqueue(store)
    publisher = OutboxPublisher(store=store, sink=sink, retry_policy=RETRY_POLICY)

    report = await publisher.publish_pending()

    assert report.retried == 1
    row = await _event(pg_sessionmaker, record.id)
    assert row.status == "pending"
    assert row.error


async def test_webhook_outbox_sink_dispatches_generic_envelope(
    local_http_server: LocalHttpServer, http_client: httpx.AsyncClient
):
    local_http_server.script("/webhooks", Reply(202))
    now = datetime(2026, 5, 22, 10, 30, tzinfo=UTC)
    sink = _webhook_sink(local_http_server, http_client)
    record = OutboxRecord(
        id="evt-1",
        event_type="generic.event",
        payload={"value": 1},
        metadata={"trace_id": "trace-1"},
    )

    await sink.publish(record, now=now)

    [request] = local_http_server.requests_to("/webhooks")
    assert request.json() == {
        "id": "evt-1",
        "type": "generic.event",
        "occurred_at": now.isoformat(),
        "payload": {"value": 1},
        "metadata": {"trace_id": "trace-1"},
    }
    assert request.headers["x-webhook-signature"].startswith("v1=")


async def test_webhook_outbox_sink_sends_once_per_publish(
    local_http_server: LocalHttpServer, http_client: httpx.AsyncClient
):
    local_http_server.script("/webhooks", Reply(503))
    sleeps: list[float] = []

    async def record_sleep(delay: float) -> None:
        sleeps.append(delay)

    sink = WebhookOutboxSink(
        url=f"{local_http_server.url}/webhooks",
        dispatcher=HttpWebhookDispatcher(
            signer=WebhookSigner(secret="secret"),
            client=http_client,
            sleep=record_sleep,
        ),
    )
    record = OutboxRecord(id="evt-1", event_type="generic.event", payload={})

    with pytest.raises(RuntimeError, match="HTTP 503"):
        await sink.publish(record, now=datetime.now(UTC))

    assert len(local_http_server.requests_to("/webhooks")) == 1
    assert sleeps == []


async def test_outbox_publisher_claims_only_its_event_family(
    pg_sessionmaker: Sessions, queue: SQSQueueGateway
):
    store = PostgresOutboxStore(pg_sessionmaker)
    task_event = await _enqueue(store, "task.created")
    other_event = await _enqueue(store, "other.event")
    publisher = OutboxPublisher(
        store=store, sink=QueueOutboxSink(queue), event_type_prefix="task."
    )

    report = await publisher.publish_pending()

    assert report.published == 1
    assert (await _event(pg_sessionmaker, task_event.id)).status == "published"
    assert (await _event(pg_sessionmaker, other_event.id)).status == "pending"
