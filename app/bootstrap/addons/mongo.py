"""Lifecycle addon for mongo; bootstrap owns open/close."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings

if TYPE_CHECKING:
    from app.bootstrap.resources import ApplicationResources
from app.modules.platform.mongo.factory import build_mongo_gateway


class MongoAddon:
    name = "mongo"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.MONGO_ENABLED

    async def open(
        self,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        resources.mongo = build_mongo_gateway(settings)

    async def close(self, resources: ApplicationResources) -> None:
        if resources.mongo is not None:
            await resources.mongo.close()
            resources.mongo = None
