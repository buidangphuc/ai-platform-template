from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.addons import BootstrapAddon
from app.core.config import Settings
from app.core.database import (
    build_engine,
    build_sessionmaker,
    check_postgres_connection,
)
from app.core.health import DependencyCheck, HealthService
from app.core.redis import build_redis_client, check_redis_connection
from app.modules.messaging.queue.factory import build_queue_gateway
from app.modules.messaging.tasks.factory import build_task_store
from app.modules.messaging.tasks.service import TaskService

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.core.resilience import RetryPolicy
    from app.modules.ai.rag.service import KnowledgeRetrievalService
    from app.modules.business.completions.pipeline import CompletionPipeline
    from app.modules.messaging.outbox.store import OutboxStore
    from app.modules.messaging.queue.gateway import QueueGateway
    from app.modules.messaging.tasks.store import TaskStore
    from app.modules.messaging.webhooks.dispatcher import HttpWebhookDispatcher
    from app.modules.messaging.webhooks.signing import WebhookSigner
    from app.modules.platform.cache.gateway import CacheGateway
    from app.modules.platform.idempotency.store import IdempotencyStore
    from app.modules.platform.objects.gateway import ObjectGateway
    from app.modules.platform.rate_limit.service import (
        InMemoryRateLimiter,
        RedisRateLimiter,
    )


@dataclass
class ApplicationResources:
    # Core infrastructure
    engine: AsyncEngine | None = None
    sessionmaker: async_sessionmaker[AsyncSession] | None = None
    redis: Redis | None = None
    queue_gateway: QueueGateway | None = None
    task_store: TaskStore | None = None
    task_service: TaskService | None = None
    # Domain pipeline
    completion_pipeline: CompletionPipeline | None = None
    # Addon-provided components
    cache: CacheGateway | None = None
    idempotency_store: IdempotencyStore | None = None
    objects: ObjectGateway | None = None
    outbox_store: OutboxStore | None = None
    principal_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None
    ip_rate_limiter: InMemoryRateLimiter | RedisRateLimiter | None = None
    rag_service: KnowledgeRetrievalService | None = None
    webhook_signer: WebhookSigner | None = None
    webhook_dispatcher: HttpWebhookDispatcher | None = None
    webhook_retry_policy: RetryPolicy | None = None
    # Lifecycle bookkeeping (close in reverse)
    addons: list[BootstrapAddon] = field(default_factory=list)


async def open_application_resources(
    app: FastAPI,
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...] = (),
) -> ApplicationResources:
    resources: ApplicationResources = app.state.resources
    validate_core_resource_requirements(
        settings=settings,
        init_resources=init_resources,
    )

    if init_resources:
        _open_database(resources, settings)
        _open_redis(resources, settings)
        _open_queue(resources, settings)
        _open_tasks(resources, settings)

    _install_health_service(app, resources, init_resources=init_resources)

    for addon in addons:
        if addon.is_enabled(settings):
            await addon.open(app, resources, settings)
            resources.addons.append(addon)

    return resources


def _open_database(resources: ApplicationResources, settings: Settings) -> None:
    if not settings.DATABASE_ENABLED:
        return
    resources.engine = build_engine(settings)
    resources.sessionmaker = build_sessionmaker(resources.engine)


def _open_redis(resources: ApplicationResources, settings: Settings) -> None:
    if not settings.REDIS_ENABLED:
        return
    resources.redis = build_redis_client(settings)


def _open_queue(resources: ApplicationResources, settings: Settings) -> None:
    if not settings.QUEUE_ENABLED:
        return
    resources.queue_gateway = build_queue_gateway(settings, redis=resources.redis)


def _open_tasks(resources: ApplicationResources, settings: Settings) -> None:
    if not settings.TASKS_ENABLED:
        return
    if resources.queue_gateway is None:
        raise RuntimeError("TASKS_ENABLED requires an open queue gateway")
    resources.task_store = build_task_store(
        settings,
        sessionmaker=resources.sessionmaker,
        redis=resources.redis,
    )

    outbox_store = None
    if settings.TASKS_DISPATCH_BACKEND == "outbox":
        if not settings.OUTBOX_ENABLED:
            raise RuntimeError("TASKS_DISPATCH_BACKEND=outbox requires OUTBOX_ENABLED")
        from app.modules.messaging.outbox.factory import build_outbox_store

        outbox_store = build_outbox_store(settings, sessionmaker=resources.sessionmaker)
        resources.outbox_store = outbox_store

    from app.modules.messaging.tasks.factory import build_task_dispatcher

    dispatcher = build_task_dispatcher(
        settings,
        queue=resources.queue_gateway,
        outbox=outbox_store,
    )
    resources.task_service = TaskService(
        store=resources.task_store,
        dispatcher=dispatcher,
        ttl_seconds=settings.TASK_TTL_SECONDS,
        lease_seconds=settings.TASKS_LEASE_SECONDS,
    )


def _install_health_service(
    app: FastAPI,
    resources: ApplicationResources,
    *,
    init_resources: bool,
) -> None:
    app.state.health_service = HealthService(
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


async def close_application_resources(app: FastAPI) -> None:
    resources: ApplicationResources = app.state.resources

    for addon in reversed(resources.addons):
        await addon.close(app, resources)
    resources.addons.clear()

    if resources.task_store is not None:
        await resources.task_store.close()
        resources.task_store = None
    if resources.queue_gateway is not None:
        await resources.queue_gateway.close()
        resources.queue_gateway = None
    if resources.redis is not None:
        await resources.redis.aclose()
        resources.redis = None
    if resources.engine is not None:
        await resources.engine.dispose()
        resources.engine = None

    app.state.health_service = HealthService(check_external_dependencies=False)
