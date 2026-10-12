"""Lifecycle addon for outbox: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

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
        stack: AsyncExitStack,
    ) -> None:
        store = build_outbox_store(
            settings,
            opened(resources.sessionmaker, "sessionmaker"),
        )
        stack.push_async_callback(store.close)
        resources.outbox_store = store
