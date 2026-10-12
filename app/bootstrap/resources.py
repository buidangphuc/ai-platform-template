from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING, TypeVar

from app.bootstrap.addons.base import BootstrapAddon
from app.core.config import Settings
from app.core.database.engine import (
    build_engine,
    build_sessionmaker,
    check_postgres_connection,
)
from app.core.health import DependencyCheck, HealthService
from app.core.redis import build_redis_client, check_redis_connection
from app.modules.messaging.queue.factory import (
    build_queue_gateway,
    build_redis_queue_gateway,
)
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.factory import (
    build_memory_task_store,
    build_postgres_task_store,
    build_redis_task_store,
)
from app.modules.messaging.tasks.outbox import PostgresTaskOutboxDispatcher
from app.modules.messaging.tasks.service import (
    QueueTaskDispatcher,
    TaskDispatcher,
    TaskService,
)
from app.modules.messaging.tasks.store import TaskStore

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.core.telemetry_otel import Telemetry
    from app.modules.ai.rag.service import KnowledgeRetrievalService
    from app.modules.business.completions.service import CompletionService
    from app.modules.messaging.outbox.store import OutboxStore
    from app.modules.messaging.webhooks.dispatcher import HttpWebhookDispatcher
    from app.modules.messaging.webhooks.signing import WebhookSigner
    from app.modules.platform.cache.gateway import CacheGateway
    from app.modules.platform.idempotency.store import IdempotencyStore
    from app.modules.platform.mongo.gateway import MongoGateway
    from app.modules.platform.objects.gateway import ObjectGateway
    from app.modules.platform.quota.service import QuotaService
    from app.modules.platform.rate_limit.service import (
        InMemoryRateLimiter,
        RedisRateLimiter,
    )


_T = TypeVar("_T")


def opened(value: _T | None, name: str) -> _T:
    """Narrow a resource that settings validation guarantees is open."""
    if value is None:
        raise RuntimeError(f"{name} is not open")
    return value


@dataclass(frozen=True)
class TaskServices:
    """Async-task feature group; exists only when ``TASKS_ENABLED``."""

    service: TaskService
    store: TaskStore
    dispatcher: TaskDispatcher
    queue: QueueGateway


@dataclass
class ApplicationResources:
    # Business services: one instance per app, composed in lifespan after the
    # platform resources below are open (see app/bootstrap/services.py).
    completion_service: CompletionService = field(init=False)
    # Core infrastructure
    engine: AsyncEngine | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None
    redis: Redis | None = None
    queue_gateway: QueueGateway | None = None
    # Feature groups
    tasks: TaskServices | None = None
    # Addon-provided components
    cache: CacheGateway | None = None
    idempotency_store: IdempotencyStore | None = None
    objects: ObjectGateway | None = None
    mongo: MongoGateway | None = None
    quota: QuotaService | None = None
    outbox_store: OutboxStore | None = None
    principal_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None
    ip_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None
    rag_service: KnowledgeRetrievalService | None = None
    webhook_signer: WebhookSigner | None = None
    webhook_dispatcher: HttpWebhookDispatcher | None = None
    telemetry: Telemetry | None = None
    # Addons opened for this runtime (closed in reverse by the exit stack)
    addons: list[BootstrapAddon] = field(default_factory=list)


@asynccontextmanager
async def open_application_resources(
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...] = (),
) -> AsyncIterator[ApplicationResources]:
    """Open every lifecycle resource once; close them in reverse on exit.

    Shared by the API lifespan and the worker, so both run the same resource
    graph. Each opener registers its own close on the exit stack.
    """
    resources = ApplicationResources()
    async with AsyncExitStack() as stack:
        if init_resources:
            _open_database(resources, settings, stack)
            _open_redis(resources, settings, stack)
            _open_queue(resources, settings, stack)

        for addon in addons:
            if addon.is_enabled(settings):
                await addon.open(resources, settings, stack)
                resources.addons.append(addon)

        if init_resources:
            _open_tasks(resources, settings, stack)

        yield resources


def _open_database(
    resources: ApplicationResources,
    settings: Settings,
    stack: AsyncExitStack,
) -> None:
    if not settings.DATABASE_ENABLED:
        return
    engine = build_engine(settings)
    stack.push_async_callback(engine.dispose)
    resources.engine = engine
    resources.sessionmaker = build_sessionmaker(engine)


def _open_redis(
    resources: ApplicationResources,
    settings: Settings,
    stack: AsyncExitStack,
) -> None:
    if not settings.REDIS_ENABLED:
        return
    redis = build_redis_client(settings)
    stack.push_async_callback(redis.aclose)
    resources.redis = redis


def _open_queue(
    resources: ApplicationResources,
    settings: Settings,
    stack: AsyncExitStack,
) -> None:
    if not settings.QUEUE_ENABLED:
        return
    match settings.QUEUE_BACKEND:
        case "redis":
            queue = build_redis_queue_gateway(
                settings, opened(resources.redis, "redis")
            )
        case "memory" | "sqs" | "rabbitmq" as backend:
            queue = build_queue_gateway(settings, backend)
    stack.push_async_callback(queue.close)
    resources.queue_gateway = queue


def _open_tasks(
    resources: ApplicationResources,
    settings: Settings,
    stack: AsyncExitStack,
) -> None:
    """Compose the task feature group (store, dispatcher, service)."""
    if not settings.TASKS_ENABLED:
        return
    queue = opened(resources.queue_gateway, "queue gateway")
    match settings.TASK_STORE_BACKEND:
        case "memory":
            store = build_memory_task_store()
        case "postgres":
            store = build_postgres_task_store(
                opened(resources.sessionmaker, "sessionmaker")
            )
        case "redis":
            store = build_redis_task_store(settings, opened(resources.redis, "redis"))
    stack.push_async_callback(store.close)

    dispatcher: TaskDispatcher
    match settings.TASKS_DISPATCH_BACKEND:
        case "queue":
            dispatcher = QueueTaskDispatcher(store, queue)
        case "outbox":
            # Settings guarantee TASK_STORE_BACKEND=postgres: the dispatcher
            # writes task + outbox event in one transaction on this sessionmaker.
            dispatcher = PostgresTaskOutboxDispatcher(
                opened(resources.sessionmaker, "sessionmaker")
            )
    resources.tasks = TaskServices(
        service=TaskService(
            store=store,
            dispatcher=dispatcher,
            ttl_seconds=settings.TASK_TTL_SECONDS,
            lease_seconds=settings.TASKS_LEASE_SECONDS,
        ),
        store=store,
        dispatcher=dispatcher,
        queue=queue,
    )


def build_health_service(
    resources: ApplicationResources,
    *,
    init_resources: bool,
) -> HealthService:
    return HealthService(
        check_external_dependencies=init_resources,
        checks=_build_dependency_checks(resources),
    )


def _build_dependency_checks(
    resources: ApplicationResources,
) -> tuple[tuple[str, DependencyCheck], ...]:
    checks: list[tuple[str, DependencyCheck]] = []
    if resources.sessionmaker is not None:
        checks.append(
            ("postgres", partial(check_postgres_connection, resources.sessionmaker))
        )
    if resources.redis is not None:
        checks.append(("redis", partial(check_redis_connection, resources.redis)))
    if resources.mongo is not None:
        from app.modules.platform.mongo.factory import check_mongo_connection

        checks.append(("mongo", partial(check_mongo_connection, resources.mongo)))
    return tuple(checks)
