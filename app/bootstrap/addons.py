from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.bootstrap.resources import ApplicationResources
    from app.core.config import Settings


@runtime_checkable
class BootstrapAddon(Protocol):
    name: str

    def is_enabled(self, settings: Settings) -> bool: ...

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None: ...

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None: ...


def addon_required_resources(
    addon: BootstrapAddon,
    settings: Settings,
) -> tuple[str, ...]:
    required_resources = getattr(addon, "required_resources", None)
    if required_resources is None:
        return ()
    return _call_required_resources(required_resources, settings)


def _call_required_resources(
    required_resources: Callable[[Settings], tuple[str, ...]] | Any,
    settings: Settings,
) -> tuple[str, ...]:
    return tuple(required_resources(settings))


def validate_addon_requirements(
    *,
    settings: Settings,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...],
) -> None:
    for addon in addons:
        if not addon.is_enabled(settings):
            continue
        for resource_name in addon_required_resources(addon, settings):
            if not _core_resource_enabled(
                resource_name,
                settings=settings,
                init_resources=init_resources,
            ):
                raise RuntimeError(
                    f"Addon {addon.name!r} requires {resource_name}, "
                    "but that core resource is disabled or resources are not "
                    "initialized"
                )


def _core_resource_enabled(
    resource_name: str,
    *,
    settings: Settings,
    init_resources: bool,
) -> bool:
    if not init_resources:
        return False
    if resource_name == "database":
        return settings.DATABASE_ENABLED
    if resource_name == "redis":
        return settings.REDIS_ENABLED
    if resource_name == "queue":
        return settings.QUEUE_ENABLED
    if resource_name == "tasks":
        return settings.TASKS_ENABLED and settings.QUEUE_ENABLED
    raise RuntimeError(f"Unknown addon resource requirement: {resource_name}")


def default_resource_addons() -> tuple[BootstrapAddon, ...]:
    from app.modules.cache.factory import CacheAddon
    from app.modules.idempotency.factory import IdempotencyAddon
    from app.modules.objects.factory import ObjectAddon
    from app.modules.outbox.factory import OutboxAddon
    from app.modules.rate_limit.factory import RateLimitAddon
    from app.modules.webhooks.factory import WebhookAddon

    return (
        RateLimitAddon(),
        IdempotencyAddon(),
        CacheAddon(),
        ObjectAddon(),
        OutboxAddon(),
        WebhookAddon(),
    )
