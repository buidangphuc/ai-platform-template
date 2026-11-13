from __future__ import annotations

import asyncio
import contextlib
import signal
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from loguru import logger


@dataclass(frozen=True)
class EventRecord:
    topic: str
    partition: int
    offset: int
    value: bytes | None
    key: bytes | None
    timestamp_ms: int


EventHandler = Callable[[Sequence[EventRecord]], Awaitable[None]]


class KafkaConsumerLoop:
    def __init__(
        self,
        *,
        consumer_factory: Callable[[], Any],
        handlers: Mapping[str, EventHandler],
        poll_timeout_ms: int,
        max_records: int,
        failure_backoff_seconds: float,
        max_backoff_seconds: float,
    ) -> None:
        self._consumer_factory = consumer_factory
        self._handlers = handlers
        self._poll_timeout_ms = poll_timeout_ms
        self._max_records = max_records
        self._base_backoff = failure_backoff_seconds
        self._max_backoff = max_backoff_seconds
        self._backoff = failure_backoff_seconds
        self._shutdown = asyncio.Event()
        self._consumer: Any = None

    def request_shutdown(self) -> None:
        self._shutdown.set()

    async def run(self, *, install_signal_handlers: bool = True) -> None:
        if install_signal_handlers:
            self._install_signal_handlers()
        consumer = self._consumer_factory()
        self._consumer = consumer
        await consumer.start()
        logger.info("events.consumer_started topics={}", sorted(self._handlers))
        try:
            while not self._shutdown.is_set():
                if not await self._drain_once():
                    await asyncio.sleep(0)
        finally:
            self._consumer = None
            await consumer.stop()
            logger.info("events.consumer_stopped")

    async def _drain_once(self) -> bool:
        batches = await self._consumer.getmany(
            timeout_ms=self._poll_timeout_ms, max_records=self._max_records
        )
        if not batches:
            return False
        pending = list(batches.items())
        while pending:
            topic_partition, records = pending.pop(0)
            if not await self._handle_partition(topic_partition, records):
                await self._rewind([(topic_partition, records), *pending])
                await self._sleep_backoff()
                break
            if self._shutdown.is_set():
                break
        return True

    async def _handle_partition(self, topic_partition: Any, records: list[Any]) -> bool:
        handler = self._handlers.get(topic_partition.topic)
        if handler is None:
            logger.warning("events.no_handler topic={}", topic_partition.topic)
            await self._commit(topic_partition, records)
            return True
        try:
            await handler([_to_event_record(record) for record in records])
        except Exception:
            logger.exception(
                "events.handler_failed topic={} partition={} first_offset={} "
                "records={} backoff={}s",
                topic_partition.topic,
                topic_partition.partition,
                records[0].offset,
                len(records),
                self._backoff,
            )
            return False
        await self._commit(topic_partition, records)
        self._backoff = self._base_backoff
        return True

    async def _commit(self, topic_partition: Any, records: list[Any]) -> None:
        await self._consumer.commit({topic_partition: records[-1].offset + 1})

    async def _rewind(self, unhandled: list[tuple[Any, list[Any]]]) -> None:
        for topic_partition, records in unhandled:
            self._consumer.seek(topic_partition, records[0].offset)

    async def _sleep_backoff(self) -> None:
        delay = self._backoff
        self._backoff = min(max(self._backoff * 2, 1.0), self._max_backoff)
        if delay <= 0:
            return
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._shutdown.wait(), timeout=delay)

    def _install_signal_handlers(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with contextlib.suppress(NotImplementedError):
                loop.add_signal_handler(sig, self.request_shutdown)


def _to_event_record(record: Any) -> EventRecord:
    return EventRecord(
        topic=record.topic,
        partition=record.partition,
        offset=record.offset,
        value=record.value,
        key=record.key,
        timestamp_ms=record.timestamp or 0,
    )
