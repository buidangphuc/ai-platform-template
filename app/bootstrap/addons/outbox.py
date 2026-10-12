"""Lifecycle addon for outbox; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.messaging.outbox.factory import build_outbox_store


class OutboxAddon:
    name = "outbox"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.OUTBOX_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        if settings.OUTBOX_BACKEND == "postgres" and not settings.DATABASE_ENABLED:
            raise RuntimeError(
                "OutboxAddon with OUTBOX_BACKEND=postgres requires DATABASE_ENABLED"
            )
        resources.outbox_store = build_outbox_store(
            settings,
            sessionmaker=resources.sessionmaker,
        )

    async def close(self, resources: ApplicationResources) -> None:
        if resources.outbox_store is not None:
            await resources.outbox_store.close()
            resources.outbox_store = None
