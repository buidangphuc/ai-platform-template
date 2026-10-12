"""Select a ``QueueGateway`` implementation based on ``Settings.QUEUE_BACKEND``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.messaging.queue.gateway import QueueGateway

if TYPE_CHECKING:
    from redis.asyncio import Redis


def build_queue_gateway(settings: Settings) -> QueueGateway:
    """Backends that need no injected client; redis uses its own builder."""
    match settings.QUEUE_BACKEND:
        case "memory":
            from app.modules.messaging.queue.adapters.memory import (
                InMemoryQueueGateway,
            )

            return InMemoryQueueGateway(name=settings.QUEUE_NAME)
        case "sqs":
            from app.modules.messaging.queue.adapters.sqs import SQSQueueGateway

            return SQSQueueGateway(
                queue_url=settings.SQS_QUEUE_URL,
                region_name=settings.SQS_REGION,
                endpoint_url=settings.SQS_ENDPOINT_URL or None,
                visibility_timeout=(
                    settings.SQS_VISIBILITY_TIMEOUT_SECONDS
                    if settings.SQS_VISIBILITY_TIMEOUT_SECONDS > 0
                    else None
                ),
            )
        case "rabbitmq":
            from app.modules.messaging.queue.adapters.rabbitmq import (
                RabbitMQQueueGateway,
            )

            return RabbitMQQueueGateway(
                url=settings.RABBITMQ_URL,
                queue_name=settings.QUEUE_NAME,
                dead_letter_enabled=settings.RABBITMQ_DEAD_LETTER_ENABLED,
                dead_letter_exchange=settings.RABBITMQ_DEAD_LETTER_EXCHANGE,
                dead_letter_queue=settings.RABBITMQ_DEAD_LETTER_QUEUE,
            )
        case backend:
            raise ValueError(f"Unknown QUEUE_BACKEND={backend!r}")


def build_redis_queue_gateway(settings: Settings, redis: Redis) -> QueueGateway:
    from app.modules.messaging.queue.adapters.redis_stream import (
        RedisStreamQueueGateway,
    )

    return RedisStreamQueueGateway(
        redis=redis,
        stream=settings.QUEUE_NAME,
        consumer_name=settings.QUEUE_REDIS_CONSUMER_NAME or None,
        min_idle_seconds=settings.QUEUE_REDIS_MIN_IDLE_SECONDS,
        max_deliveries=settings.QUEUE_REDIS_MAX_DELIVERIES,
    )
