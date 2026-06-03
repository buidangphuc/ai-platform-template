from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.mongo import build_mongo_client
from app.modules.platform.mongo.gateway import MongoGateway

if TYPE_CHECKING:
    from fastapi import FastAPI

    from app.bootstrap.resources import ApplicationResources


def build_mongo_gateway(settings: Settings) -> MongoGateway:
    return MongoGateway(
        build_mongo_client(settings),
        database=settings.MONGODB_DATABASE,
    )


async def check_mongo_connection(gateway: MongoGateway) -> None:
    await gateway.ping()


class MongoAddon:
    name = "mongo"

    def is_enabled(self, settings: Settings) -> bool:
        return settings.MONGO_ENABLED

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        resources.mongo = build_mongo_gateway(settings)

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        if resources.mongo is not None:
            await resources.mongo.close()
            resources.mongo = None
