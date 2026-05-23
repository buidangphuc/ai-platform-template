"""Select a ``QueueGateway`` implementation based on ``Settings.QUEUE_BACKEND``."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.messaging.queue.gateway import QueueGateway

if TYPE_CHECKING:
    from redis.asyncio import Redis


def build_queue_gateway(
    settings: Settings,
    *,
    redis: Redis | None = None,
) -> QueueGateway:
    backend = settings.QUEUE_BACKEND

    if backend == "memory":
        from app.modules.messaging.queue.adapters.memory import InMemoryQueueGateway

        return InMemoryQueueGateway(name=settings.QUEUE_NAME)

    if backend == "redis":
        if redis is None:
            raise RuntimeError("redis client is required for redis queue backend")
        from app.modules.messaging.queue.adapters.redis_stream import (
            RedisStreamQueueGateway,
        )

        return RedisStreamQueueGateway(redis=redis, stream=settings.QUEUE_NAME)

    if backend == "sqs":
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

    if backend == "rabbitmq":
        from app.modules.messaging.queue.adapters.rabbitmq import RabbitMQQueueGateway

        return RabbitMQQueueGateway(
            url=settings.RABBITMQ_URL,
            queue_name=settings.QUEUE_NAME,
        )

    raise ValueError(f"Unknown QUEUE_BACKEND={backend!r}")
