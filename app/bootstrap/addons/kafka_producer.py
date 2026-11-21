from __future__ import annotations

from contextlib import AsyncExitStack
from functools import partial

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.messaging.events.factory import build_kafka_producer
from app.modules.messaging.events.producer import KafkaEventProducer


class KafkaProducerAddon:
    name = "kafka_producer"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.KAFKA_PRODUCER_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        producer = KafkaEventProducer(partial(build_kafka_producer, settings))
        await producer.start()
        stack.push_async_callback(producer.stop)
        resources.event_producer = producer
