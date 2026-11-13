from __future__ import annotations

from collections.abc import Callable
from typing import Any


class KafkaEventProducer:
    def __init__(self, producer_factory: Callable[[], Any]) -> None:
        self._producer_factory = producer_factory
        self._producer: Any = None

    async def start(self) -> None:
        producer = self._producer_factory()
        await producer.start()
        self._producer = producer

    async def stop(self) -> None:
        producer, self._producer = self._producer, None
        if producer is not None:
            await producer.stop()

    async def send(self, topic: str, *, key: bytes, value: bytes) -> None:
        if self._producer is None:
            raise RuntimeError("Kafka producer is not started")
        await self._producer.send_and_wait(topic, value=value, key=key)
