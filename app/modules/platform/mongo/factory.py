from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.config import Settings
from app.core.mongo import build_mongo_client
from app.modules.platform.mongo.gateway import MongoGateway

if TYPE_CHECKING:
    pass


def build_mongo_gateway(settings: Settings) -> MongoGateway:
    return MongoGateway(
        build_mongo_client(settings),
        database=settings.MONGODB_DATABASE,
    )


async def check_mongo_connection(gateway: MongoGateway) -> None:
    await gateway.ping()
