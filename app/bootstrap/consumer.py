from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from functools import partial

from app.bootstrap.addons.base import default_resource_addons
from app.bootstrap.features.base import ConsumerHandler, Feature
from app.bootstrap.features.registry import FEATURES
from app.bootstrap.resources import ApplicationResources
from app.bootstrap.services import enabled_features, open_runtime
from app.core.config import Settings, get_settings
from app.modules.messaging.events.consumer import EventHandler, KafkaConsumerLoop
from app.modules.messaging.events.factory import build_kafka_consumer


@dataclass
class ConsumerContext:
    loop: KafkaConsumerLoop
    resources: ApplicationResources
    topics: tuple[str, ...]

    async def run(self) -> None:
        await self.loop.run()


def consumer_handlers(
    settings: Settings, features: tuple[Feature, ...]
) -> dict[str, ConsumerHandler]:
    handlers: dict[str, ConsumerHandler] = {}
    owners: dict[str, str] = {}
    for feature in features:
        for topic, handler in feature.consumers(settings).items():
            if topic in handlers:
                raise ValueError(
                    f"consumer topic {topic!r} declared by features "
                    f"{owners[topic]!r} and {feature.name!r}"
                )
            handlers[topic] = handler
            owners[topic] = feature.name
    return handlers


def validate_consumer_runtime_settings(
    settings: Settings, handlers: Mapping[str, ConsumerHandler]
) -> None:
    if not settings.KAFKA_CONSUMER_ENABLED:
        raise RuntimeError("Consumer requires KAFKA_CONSUMER_ENABLED")
    if not handlers:
        raise RuntimeError(
            "Consumer requires an enabled feature that declares a consumer"
        )


@asynccontextmanager
async def consumer_context(
    settings: Settings | None = None,
    *,
    features: tuple[Feature, ...] = FEATURES,
) -> AsyncIterator[ConsumerContext]:
    resolved = settings or get_settings()
    enabled = enabled_features(resolved, features)
    handlers = consumer_handlers(resolved, enabled)
    validate_consumer_runtime_settings(resolved, handlers)
    topics = tuple(handlers)
    async with open_runtime(
        resolved,
        init_resources=True,
        addons=default_resource_addons(),
        features=features,
    ) as resources:
        bound: dict[str, EventHandler] = {
            topic: partial(handler, resources) for topic, handler in handlers.items()
        }
        yield ConsumerContext(
            loop=KafkaConsumerLoop(
                consumer_factory=lambda: build_kafka_consumer(resolved, topics),
                handlers=bound,
                poll_timeout_ms=resolved.KAFKA_POLL_TIMEOUT_MS,
                max_records=resolved.KAFKA_MAX_POLL_RECORDS,
                failure_backoff_seconds=resolved.KAFKA_FAILURE_BACKOFF_SECONDS,
                max_backoff_seconds=resolved.KAFKA_MAX_BACKOFF_SECONDS,
            ),
            resources=resources,
            topics=topics,
        )
