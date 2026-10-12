"""Lifecycle addon for mongo: opens it and registers its close on the stack."""

from __future__ import annotations

from contextlib import AsyncExitStack

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.mongo.factory import build_mongo_gateway


class MongoAddon:
    name = "mongo"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.MONGO_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
        stack: AsyncExitStack,
    ) -> None:
        gateway = build_mongo_gateway(settings)
        stack.push_async_callback(gateway.close)
        resources.mongo = gateway
