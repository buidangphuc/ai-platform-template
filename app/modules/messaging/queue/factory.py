"""Open a ``QueueGateway`` implementation based on ``Settings.QUEUE_BACKEND``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from app.core.config import Settings
from app.modules.messaging.queue.gateway import QueueGateway

if TYPE_CHECKING:
    from redis.asyncio import Redis


ClientlessQueueBackend = Literal["memory", "sqs", "rabbitmq"]


async def open_queue_gateway(
    settings: Settings,
    backend: ClientlessQueueBackend,
) -> QueueGateway:
    """Backends that need no injected client; redis uses its own builder.

    The SQS and RabbitMQ gateways connect here, so an unreachable broker fails
    startup instead of the first request.
    """
    match backend:
        case "memory":
            from app.modules.messaging.queue.adapters.memory import (
                InMemoryQueueGateway,
            )

            return InMemoryQueueGateway(name=settings.QUEUE_NAME)
        case "sqs":
            from app.modules.messaging.queue.adapters.sqs import SQSQueueGateway

            return await SQSQueueGateway(
                queue_url=settings.SQS_QUEUE_URL,
                region_name=settings.SQS_REGION,
                endpoint_url=settings.SQS_ENDPOINT_URL or None,
                visibility_timeout=(
                    settings.SQS_VISIBILITY_TIMEOUT_SECONDS
                    if settings.SQS_VISIBILITY_TIMEOUT_SECONDS > 0
                    else None
                ),
            ).open()
        case "rabbitmq":
            from app.modules.messaging.queue.adapters.rabbitmq import (
                RabbitMQQueueGateway,
            )

            return await RabbitMQQueueGateway(
                url=settings.RABBITMQ_URL,
                queue_name=settings.QUEUE_NAME,
                dead_letter_enabled=settings.RABBITMQ_DEAD_LETTER_ENABLED,
                dead_letter_exchange=settings.RABBITMQ_DEAD_LETTER_EXCHANGE,
                dead_letter_queue=settings.RABBITMQ_DEAD_LETTER_QUEUE,
            ).open()


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
        dead_letter_maxlen=settings.QUEUE_REDIS_DEAD_LETTER_MAXLEN,
    )
