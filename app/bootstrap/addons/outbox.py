"""Lifecycle addon for outbox; bootstrap owns open/close."""

from __future__ import annotations

from app.bootstrap.resources import ApplicationResources, opened
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
        resources.outbox_store = build_outbox_store(
            settings,
            opened(resources.sessionmaker, "sessionmaker"),
        )

    async def close(self, resources: ApplicationResources) -> None:
        await opened(resources.outbox_store, "outbox store").close()
