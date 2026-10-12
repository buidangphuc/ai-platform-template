"""Lifecycle addon for mongo; bootstrap owns open/close."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.modules.platform.mongo.factory import build_mongo_gateway
from app.modules.platform.mongo.gateway import MongoGateway

if TYPE_CHECKING:
    from app.bootstrap.resources import ApplicationResources


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
        await _mongo(resources).close()


def _mongo(resources: ApplicationResources) -> MongoGateway:
    if resources.mongo is None:
        raise RuntimeError("MongoAddon has no open gateway")
    return resources.mongo
