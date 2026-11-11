from collections.abc import Callable

import pytest
from pymongo.errors import InvalidOperation, ServerSelectionTimeoutError

from app.bootstrap.addons.mongo import MongoAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.mongo.factory import (
    build_mongo_gateway,
    check_mongo_connection,
)
from app.modules.platform.mongo.gateway import MongoGateway
from tests.factories import open_addon
from tests.infra import require


@pytest.fixture()
def mongo_settings(
    infra_settings: Callable[..., Settings], mongo_gateway: MongoGateway
) -> Callable[..., Settings]:
    def build(**overrides: object) -> Settings:
        values: dict[str, object] = {
            "MONGO_ENABLED": True,
            "MONGODB_URI": require("mongo"),
            "MONGODB_DATABASE": mongo_gateway.database.name,
            "MONGODB_SERVER_SELECTION_TIMEOUT_MS": 500,
        }
        values.update(overrides)
        return infra_settings(**values)

    return build


async def test_mongo_gateway_scopes_client_to_database(mongo_gateway: MongoGateway):
    collection = mongo_gateway.collection("items")

    await collection.insert_one({"_id": "a", "value": 1})

    assert collection.name == "items"
    assert collection.database.name == mongo_gateway.database.name
    assert await mongo_gateway.database["items"].find_one({"_id": "a"}) == {
        "_id": "a",
        "value": 1,
    }
    assert (
        "items"
        in await mongo_gateway.client[
            mongo_gateway.database.name
        ].list_collection_names()
    )


async def test_mongo_gateway_ping_and_close(mongo_settings):
    gateway = build_mongo_gateway(mongo_settings())

    assert (await gateway.ping())["ok"] == 1
    await gateway.close()

    with pytest.raises(InvalidOperation):
        await gateway.ping()


async def test_check_mongo_connection_pings_gateway(mongo_gateway: MongoGateway):
    await check_mongo_connection(mongo_gateway)


async def test_check_mongo_connection_fails_when_the_server_is_unreachable(
    mongo_settings,
):
    gateway = build_mongo_gateway(mongo_settings(MONGODB_URI="mongodb://127.0.0.1:1"))

    try:
        with pytest.raises(ServerSelectionTimeoutError):
            await check_mongo_connection(gateway)
    finally:
        await gateway.close()


async def test_build_mongo_gateway_uses_settings(mongo_settings):
    settings = mongo_settings()

    gateway = build_mongo_gateway(settings)

    try:
        assert gateway.database.name == settings.MONGODB_DATABASE
        assert (await gateway.ping())["ok"] == 1
    finally:
        await gateway.close()


async def test_mongo_addon_opens_and_closes_gateway(mongo_settings):
    settings = mongo_settings()
    resources = ApplicationResources()
    addon = MongoAddon()

    assert addon.is_enabled(settings) is True
    stack = await open_addon(addon, resources, settings)

    gateway = resources.mongo
    assert isinstance(gateway, MongoGateway)
    [(name, check)] = resources.health_checks.checks
    assert name == "mongo"
    await check()

    await stack.aclose()

    with pytest.raises(InvalidOperation):
        await gateway.ping()
