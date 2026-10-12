from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from contextlib import AsyncExitStack

    from app.bootstrap.resources import ApplicationResources
    from app.core.config import Settings


class BootstrapAddon(Protocol):
    name: str

    def is_enabled(self, settings: Settings) -> bool: ...

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        """Open the capability onto ``resources``; push its close onto ``stack``."""
        ...


def default_resource_addons() -> tuple[BootstrapAddon, ...]:
    from app.bootstrap.addons.cache import CacheAddon
    from app.bootstrap.addons.idempotency import IdempotencyAddon
    from app.bootstrap.addons.mongo import MongoAddon
    from app.bootstrap.addons.objects import ObjectAddon
    from app.bootstrap.addons.outbox import OutboxAddon
    from app.bootstrap.addons.quota import QuotaAddon
    from app.bootstrap.addons.rag import RagAddon
    from app.bootstrap.addons.rate_limit import RateLimitAddon
    from app.bootstrap.addons.telemetry import TelemetryAddon
    from app.bootstrap.addons.webhooks import WebhookAddon

    return (
        TelemetryAddon(),
        RateLimitAddon(),
        IdempotencyAddon(),
        CacheAddon(),
        ObjectAddon(),
        MongoAddon(),
        QuotaAddon(),
        OutboxAddon(),
        WebhookAddon(),
        RagAddon(),
    )
