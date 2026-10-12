"""Messaging settings: queue, tasks + worker, outbox, webhooks."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MessagingSettingsMixin(BaseModel):
    # Queue gateway
    QUEUE_ENABLED: bool = False
    QUEUE_BACKEND: str = "memory"
    QUEUE_NAME: str = "completions"
    SQS_QUEUE_URL: str = ""
    SQS_REGION: str = "ap-southeast-1"
    SQS_ENDPOINT_URL: str = ""
    SQS_VISIBILITY_TIMEOUT_SECONDS: int = Field(default=0, ge=0)
    RABBITMQ_URL: str = ""
    # Dead-letter topology for the work queue. Empty names derive from
    # QUEUE_NAME (<name>.dlx / <name>.dead). Set ENABLED=false to keep declaring
    # a pre-existing queue that has no DLX arguments (RabbitMQ rejects
    # re-declaring a queue with different arguments).
    RABBITMQ_DEAD_LETTER_ENABLED: bool = True
    RABBITMQ_DEAD_LETTER_EXCHANGE: str = ""
    RABBITMQ_DEAD_LETTER_QUEUE: str = ""
    # Redis Streams redelivery. CONSUMER_NAME empty -> $HOSTNAME -> random.
    # MIN_IDLE must exceed the slowest handler, else live work is reclaimed.
    QUEUE_REDIS_CONSUMER_NAME: str = ""
    QUEUE_REDIS_MIN_IDLE_SECONDS: float = Field(default=60.0, gt=0)
    QUEUE_REDIS_MAX_DELIVERIES: int = Field(default=5, gt=0)

    # Async task store + service
    TASKS_ENABLED: bool = False
    TASK_STORE_BACKEND: str = "memory"
    TASK_REDIS_PREFIX: str = "tasks"
    TASK_TTL_SECONDS: int = Field(default=86_400, gt=0)
    TASKS_LEASE_SECONDS: int = Field(default=300, gt=0)
    TASKS_DISPATCH_BACKEND: str = "queue"

    # Polling worker
    WORKER_MAX_CONCURRENT: int = Field(default=10, gt=0)
    WORKER_MAX_ATTEMPTS: int = Field(default=3, gt=0)
    WORKER_POLL_INTERVAL_SECONDS: float = Field(default=0.5, ge=0)
    WORKER_RECEIVE_BATCH_SIZE: int = Field(default=10, gt=0)
    WORKER_RECEIVE_WAIT_SECONDS: float = Field(default=1.0, ge=0)

    # Outbox (transactional event publication)
    OUTBOX_ENABLED: bool = False
    OUTBOX_BACKEND: str = "postgres"

    # Webhook delivery
    WEBHOOKS_ENABLED: bool = False
    WEBHOOK_SIGNING_SECRET: str = ""
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS: int = Field(default=300, gt=0)
    WEBHOOK_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)
