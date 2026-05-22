from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import FastAPI

from app.bootstrap.addons import BootstrapAddon, validate_addon_requirements
from app.bootstrap.manifest import BootstrapManifest, build_bootstrap_manifest
from app.bootstrap.state import attach_app_resource, clear_app_resource
from app.core.config import Settings
from app.core.database import (
    build_engine,
    build_sessionmaker,
    check_postgres_connection,
)
from app.core.health import DependencyCheck, HealthService
from app.core.redis import build_redis_client, check_redis_connection
from app.modules.queue.factory import build_queue_gateway
from app.modules.tasks.factory import build_task_store
from app.modules.tasks.service import TaskService

if TYPE_CHECKING:
    from redis.asyncio import Redis
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

    from app.modules.queue.gateway import QueueGateway
    from app.modules.tasks.store import TaskStore


@dataclass
class ApplicationResources:
    engine: "AsyncEngine | None" = None
    sessionmaker: "async_sessionmaker[AsyncSession] | None" = None
    redis: "Redis | None" = None
    queue_gateway: "QueueGateway | None" = None
    task_store: "TaskStore | None" = None
    task_service: TaskService | None = None
    health_service: HealthService | None = None
    manifest: BootstrapManifest | None = None
    addons: list[BootstrapAddon] = field(default_factory=list)
    state_keys: list[str] = field(default_factory=list)


async def open_application_resources(
    app: FastAPI,
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...] = (),
) -> ApplicationResources:
    resources = ApplicationResources()
    attach_app_resource(app, resources, "resources", resources)
    manifest = getattr(app.state, "bootstrap_manifest", None)
    if manifest is None:
        manifest = build_bootstrap_manifest(
            settings=settings,
            init_resources=init_resources,
            addons=addons,
        )
        app.state.bootstrap_manifest = manifest
    resources.manifest = manifest
    validate_core_resource_requirements(
        settings=settings,
        init_resources=init_resources,
    )
    validate_addon_requirements(
        settings=settings,
        init_resources=init_resources,
        addons=addons,
    )

    database_enabled = init_resources and settings.DATABASE_ENABLED
    redis_enabled = init_resources and settings.REDIS_ENABLED
    queue_enabled = init_resources and settings.QUEUE_ENABLED
    tasks_enabled = init_resources and settings.TASKS_ENABLED

    if tasks_enabled and not queue_enabled:
        raise RuntimeError("TASKS_ENABLED requires QUEUE_ENABLED")

    if database_enabled:
        resources.engine = build_engine(settings)
        resources.sessionmaker = build_sessionmaker(resources.engine)
        attach_app_resource(app, resources, "engine", resources.engine)
        attach_app_resource(app, resources, "sessionmaker", resources.sessionmaker)
        manifest.mark_resource_opened("database")

    if redis_enabled:
        resources.redis = build_redis_client(settings)
        attach_app_resource(app, resources, "redis", resources.redis)
        manifest.mark_resource_opened("redis")

    if queue_enabled:
        resources.queue_gateway = build_queue_gateway(settings, redis=resources.redis)
        attach_app_resource(app, resources, "queue_gateway", resources.queue_gateway)
        manifest.mark_resource_opened("queue")

    if tasks_enabled:
        queue_gateway = resources.queue_gateway
        if queue_gateway is None:
            raise RuntimeError("TASKS_ENABLED requires an open queue gateway")
        resources.task_store = build_task_store(
            settings,
            sessionmaker=resources.sessionmaker,
            redis=resources.redis,
        )
        resources.task_service = TaskService(
            store=resources.task_store,
            queue=queue_gateway,
            ttl_seconds=settings.TASK_TTL_SECONDS,
        )
        attach_app_resource(app, resources, "task_store", resources.task_store)
        attach_app_resource(app, resources, "task_service", resources.task_service)
        manifest.mark_resource_opened("tasks")

    postgres_check: DependencyCheck | None = None
    if resources.sessionmaker is not None:
        sessionmaker = resources.sessionmaker

        async def _postgres_check() -> None:
            return await check_postgres_connection(sessionmaker)

        postgres_check = _postgres_check

    redis_check: DependencyCheck | None = None
    if resources.redis is not None:
        redis = resources.redis

        async def _redis_check() -> None:
            return await check_redis_connection(redis)

        redis_check = _redis_check

    resources.health_service = HealthService(
        check_external_dependencies=init_resources,
        postgres_check=postgres_check,
        redis_check=redis_check,
    )
    app.state.health_service = resources.health_service

    for addon in addons:
        if addon.is_enabled(settings):
            await addon.open(app, resources, settings)
            resources.addons.append(addon)
            manifest.mark_addon_opened(addon.name)
    return resources


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


async def close_application_resources(app: FastAPI | None) -> None:
    if app is None:
        return

    resources = getattr(app.state, "resources", None)
    task_store = resources.task_store if resources is not None else None
    queue_gateway = resources.queue_gateway if resources is not None else None
    redis = resources.redis if resources is not None else None
    engine = resources.engine if resources is not None else None

    if resources is not None:
        for addon in reversed(resources.addons):
            await addon.close(app, resources)
            if resources.manifest is not None:
                resources.manifest.mark_addon_closed(addon.name)

    if task_store is not None:
        await task_store.close()
        if resources is not None and resources.manifest is not None:
            resources.manifest.mark_resource_closed("tasks")

    if queue_gateway is not None:
        await queue_gateway.close()
        if resources is not None and resources.manifest is not None:
            resources.manifest.mark_resource_closed("queue")

    if redis is not None and hasattr(redis, "aclose"):
        await redis.aclose()
        if resources is not None and resources.manifest is not None:
            resources.manifest.mark_resource_closed("redis")

    if engine is not None and hasattr(engine, "dispose"):
        await engine.dispose()
        if resources is not None and resources.manifest is not None:
            resources.manifest.mark_resource_closed("database")

    if resources is not None:
        for state_key in reversed(resources.state_keys):
            clear_app_resource(app, state_key)

    app.state.health_service = HealthService(check_external_dependencies=False)
