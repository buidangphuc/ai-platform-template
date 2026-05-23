from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

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


def default_resource_addons() -> tuple[BootstrapAddon, ...]:
    from app.modules.ai.rag.factory import RagAddon
    from app.modules.messaging.outbox.factory import OutboxAddon
    from app.modules.messaging.webhooks.factory import WebhookAddon
    from app.modules.platform.cache.factory import CacheAddon
    from app.modules.platform.idempotency.factory import IdempotencyAddon
    from app.modules.platform.objects.factory import ObjectAddon
    from app.modules.platform.rate_limit.factory import RateLimitAddon

    return (
        RateLimitAddon(),
        IdempotencyAddon(),
        CacheAddon(),
        ObjectAddon(),
        OutboxAddon(),
        WebhookAddon(),
        RagAddon(),
    )
