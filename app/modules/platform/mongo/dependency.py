from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from app.bootstrap.state import get_mongo_gateway
from app.modules.platform.mongo.gateway import MongoGateway


def get_mongo(request: Request) -> MongoGateway:
    return get_mongo_gateway(request.app)


MongoDep = Annotated[MongoGateway, Depends(get_mongo)]
