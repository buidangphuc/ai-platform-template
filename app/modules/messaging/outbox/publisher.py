from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol, runtime_checkable

from app.core.resilience import RetryPolicy
from app.modules.messaging.outbox.store import OutboxRecord, OutboxStore
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.webhooks.dispatcher import HttpWebhookDispatcher
from app.modules.messaging.webhooks.envelope import WebhookEnvelope


@runtime_checkable
class OutboxSink(Protocol):
    async def publish(self, record: OutboxRecord, *, now: datetime) -> None: ...


@dataclass(frozen=True)
class OutboxPublishReport:
    total: int
    published: int
    retried: int
    failed: int


class QueueOutboxSink:
    def __init__(self, queue: QueueGateway) -> None:
        self.queue = queue

    async def publish(self, record: OutboxRecord, *, now: datetime) -> None:
        await self.queue.send(outbox_queue_payload(record))


class WebhookOutboxSink:
    def __init__(self, *, url: str, dispatcher: HttpWebhookDispatcher) -> None:
        self.url = url
        self.dispatcher = dispatcher

    async def publish(self, record: OutboxRecord, *, now: datetime) -> None:
        result = await self.dispatcher.dispatch(
            self.url,
            WebhookEnvelope(
                id=record.id,
                type=record.event_type,
                occurred_at=now,
                payload=record.payload,
                metadata=record.metadata,
            ),
        )
        if not result.succeeded:
            reason = result.error or f"HTTP {result.status_code}"
            raise RuntimeError(reason)


class OutboxPublisher:
    def __init__(
        self,
        *,
        store: OutboxStore,
        sink: OutboxSink,
        retry_policy: RetryPolicy | None = None,
    ) -> None:
        self.store = store
        self.sink = sink
        self.retry_policy = retry_policy or RetryPolicy()

    async def publish_pending(
        self,
        *,
        limit: int = 100,
        now: datetime | None = None,
        lock_seconds: float = 60.0,
    ) -> OutboxPublishReport:
        if lock_seconds <= 0:
            raise ValueError("lock_seconds must be positive")
        now = now or datetime.now(UTC)
        records = await self.store.claim_pending(
            limit=limit,
            now=now,
            lock_seconds=lock_seconds,
        )
        published = 0
        retried = 0
        failed = 0

        for record in records:
            try:
                await self.sink.publish(record, now=now)
            except Exception as exc:
                decision = self.retry_policy.decision(
                    attempt=record.attempts + 1,
                    error=exc,
                )
                if decision.should_retry:
                    retried += 1
                    delay = decision.next_delay_seconds or 0.0
                    await self.store.mark_failed(
                        record.id,
                        error=str(exc),
                        available_at=now + timedelta(seconds=delay),
                    )
                else:
                    failed += 1
                    await self.store.mark_failed(record.id, error=str(exc))
            else:
                published += 1
                await self.store.mark_published(record.id, published_at=now)

        return OutboxPublishReport(
            total=len(records),
            published=published,
            retried=retried,
            failed=failed,
        )


def outbox_queue_payload(record: OutboxRecord) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": record.id,
        "type": record.event_type,
        "payload": record.payload,
        "metadata": record.metadata,
    }
    return payload
