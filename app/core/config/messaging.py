"""Messaging settings: queue, tasks + worker, outbox, webhooks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

QueueBackend = Literal["memory", "redis", "sqs", "rabbitmq"]
TaskStoreBackend = Literal["memory", "postgres", "redis"]
TaskDispatchBackend = Literal["queue", "outbox"]
OutboxBackend = Literal["postgres"]


class MessagingSettingsMixin(BaseModel):
    # Declared by InfraSettingsMixin; annotated here so the cross-setting
    # rules below can read them.
    DATABASE_ENABLED: bool
    REDIS_ENABLED: bool

    # Queue gateway
    QUEUE_ENABLED: bool = False
    QUEUE_BACKEND: QueueBackend = "memory"
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
    TASK_STORE_BACKEND: TaskStoreBackend = "memory"
    TASK_REDIS_PREFIX: str = "tasks"
    TASK_TTL_SECONDS: int = Field(default=86_400, gt=0)
    TASKS_LEASE_SECONDS: int = Field(default=300, gt=0)
    TASKS_DISPATCH_BACKEND: TaskDispatchBackend = "queue"

    # Polling worker
    WORKER_MAX_CONCURRENT: int = Field(default=10, gt=0)
    WORKER_MAX_ATTEMPTS: int = Field(default=3, gt=0)
    WORKER_POLL_INTERVAL_SECONDS: float = Field(default=0.5, ge=0)
    WORKER_RECEIVE_BATCH_SIZE: int = Field(default=10, gt=0)
    WORKER_RECEIVE_WAIT_SECONDS: float = Field(default=1.0, ge=0)

    # Outbox (transactional event publication)
    OUTBOX_ENABLED: bool = False
    OUTBOX_BACKEND: OutboxBackend = "postgres"

    # Webhook delivery
    WEBHOOKS_ENABLED: bool = False
    WEBHOOK_SIGNING_SECRET: str = ""
    WEBHOOK_TIMESTAMP_TOLERANCE_SECONDS: int = Field(default=300, gt=0)
    WEBHOOK_TIMEOUT_SECONDS: float = Field(default=10.0, gt=0)

    @model_validator(mode="after")
    def validate_messaging_requirements(self) -> MessagingSettingsMixin:
        if self.QUEUE_ENABLED and self.QUEUE_BACKEND == "redis":
            _require(self.REDIS_ENABLED, "QUEUE_BACKEND=redis requires REDIS_ENABLED")
        if self.TASKS_ENABLED:
            _require(self.QUEUE_ENABLED, "TASKS_ENABLED requires QUEUE_ENABLED")
            if self.TASK_STORE_BACKEND == "postgres":
                _require(
                    self.DATABASE_ENABLED,
                    "TASK_STORE_BACKEND=postgres requires DATABASE_ENABLED",
                )
            if self.TASK_STORE_BACKEND == "redis":
                _require(
                    self.REDIS_ENABLED,
                    "TASK_STORE_BACKEND=redis requires REDIS_ENABLED",
                )
            if self.TASKS_DISPATCH_BACKEND == "outbox":
                _require(
                    self.OUTBOX_ENABLED,
                    "TASKS_DISPATCH_BACKEND=outbox requires OUTBOX_ENABLED",
                )
        if self.OUTBOX_ENABLED and self.OUTBOX_BACKEND == "postgres":
            _require(
                self.DATABASE_ENABLED,
                "OUTBOX_BACKEND=postgres requires DATABASE_ENABLED",
            )
        if self.WEBHOOKS_ENABLED:
            _require(
                bool(self.WEBHOOK_SIGNING_SECRET),
                "WEBHOOK_SIGNING_SECRET is required when WEBHOOKS_ENABLED is true",
            )
        return self


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)
