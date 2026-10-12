from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from app.bootstrap.addons.base import BootstrapAddon
from app.core.config import Settings
from app.core.database.engine import (
    build_engine,
    build_sessionmaker,
    check_postgres_connection,
)
from app.core.health import DependencyCheck, HealthService
from app.core.redis import build_redis_client, check_redis_connection
from app.modules.messaging.queue.factory import build_queue_gateway
from app.modules.messaging.queue.gateway import QueueGateway
from app.modules.messaging.tasks.factory import build_task_store
from app.modules.messaging.tasks.service import TaskDispatcher, TaskService
from app.modules.messaging.tasks.store import TaskStore

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.core.resilience import RetryPolicy
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
    webhook_retry_policy: RetryPolicy | None = None
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
    validate_core_resource_requirements(
        settings=settings,
        init_resources=init_resources,
    )
    resources = ApplicationResources()
    async with AsyncExitStack() as stack:
        if init_resources:
            _open_database(resources, settings, stack)
            _open_redis(resources, settings, stack)
            _open_queue(resources, settings, stack)

        for addon in addons:
            if addon.is_enabled(settings):
                await addon.open(resources, settings)
                stack.push_async_callback(addon.close, resources)
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
    queue = build_queue_gateway(settings, redis=resources.redis)
    stack.push_async_callback(queue.close)
    resources.queue_gateway = queue


def _open_tasks(
    resources: ApplicationResources,
    settings: Settings,
    stack: AsyncExitStack,
) -> None:
    """Runs after addons so the outbox dispatcher reuses OutboxAddon's store."""
    if not settings.TASKS_ENABLED:
        return
    if resources.queue_gateway is None:
        raise RuntimeError("TASKS_ENABLED requires an open queue gateway")
    store = build_task_store(
        settings,
        sessionmaker=resources.sessionmaker,
        redis=resources.redis,
    )
    stack.push_async_callback(store.close)

    from app.modules.messaging.tasks.factory import build_task_dispatcher

    dispatcher = build_task_dispatcher(
        settings,
        queue=resources.queue_gateway,
        outbox=resources.outbox_store,
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
        queue=resources.queue_gateway,
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


def validate_core_resource_requirements(
    *,
    settings: Settings,
    init_resources: bool,
) -> None:
    if not init_resources:
        return
    if settings.TASKS_ENABLED and not settings.QUEUE_ENABLED:
        raise RuntimeError("TASKS_ENABLED requires QUEUE_ENABLED")
    if settings.TASKS_DISPATCH_BACKEND == "outbox" and settings.TASKS_ENABLED:
        _require_enabled(
            settings.OUTBOX_ENABLED,
            "TASKS_DISPATCH_BACKEND=outbox requires OUTBOX_ENABLED",
        )
    if settings.QUEUE_ENABLED and settings.QUEUE_BACKEND == "redis":
        _require_enabled(
            settings.REDIS_ENABLED,
            "QUEUE_BACKEND=redis requires REDIS_ENABLED",
        )
    if settings.TASKS_ENABLED and settings.TASK_STORE_BACKEND == "postgres":
        _require_enabled(
            settings.DATABASE_ENABLED,
            "TASK_STORE_BACKEND=postgres requires DATABASE_ENABLED",
        )
    if settings.TASKS_ENABLED and settings.TASK_STORE_BACKEND == "redis":
        _require_enabled(
            settings.REDIS_ENABLED,
            "TASK_STORE_BACKEND=redis requires REDIS_ENABLED",
        )


def _require_enabled(enabled: bool, message: str) -> None:
    if not enabled:
        raise RuntimeError(message)
