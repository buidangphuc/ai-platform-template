"""Lifecycle addon for idempotency: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources, opened
from app.core.config import Settings
from app.modules.platform.idempotency.factory import build_idempotency_store


class IdempotencyAddon:
    name = "idempotency"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.IDEMPOTENCY_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        store = build_idempotency_store(
            settings,
            sessionmaker=opened(resources.sessionmaker, "sessionmaker"),
        )
        stack.push_async_callback(store.close)
        resources.idempotency_store = store
