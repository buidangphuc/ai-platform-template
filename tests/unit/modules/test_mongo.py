import pytest
from fastapi import FastAPI
from starlette.requests import Request

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.core.errors import ServiceUnavailableError
from app.modules.platform.mongo.dependency import get_mongo
from app.modules.platform.mongo.factory import (
    MongoAddon,
    build_mongo_gateway,
    check_mongo_connection,
)
from app.modules.platform.mongo.gateway import MongoGateway


class _FakeAdmin:
    def __init__(self) -> None:
        self.commands: list[str] = []

    async def command(self, command: str):
        self.commands.append(command)
        return {"ok": 1}


class _FakeDatabase(dict[str, object]):
    def __getitem__(self, collection: str) -> object:
        if collection not in self:
            self[collection] = object()
        return dict.__getitem__(self, collection)


class _FakeClient:
    def __init__(self) -> None:
        self.admin = _FakeAdmin()
        self.closed = False
        self.databases: dict[str, _FakeDatabase] = {}

    def __getitem__(self, database: str) -> "_FakeDatabase":
        return self.databases.setdefault(database, _FakeDatabase())

    def close(self) -> None:
        self.closed = True


def _request_for(app: FastAPI) -> Request:
    return Request(
        {
            "type": "http",
            "app": app,
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )


def test_mongo_gateway_scopes_client_to_database():
    client = _FakeClient()
    gateway = MongoGateway(client, database="app")

    assert gateway.client is client
    assert gateway.database is client.databases["app"]
    assert gateway.collection("items") is gateway.database["items"]


async def test_mongo_gateway_ping_and_close():
    client = _FakeClient()
    gateway = MongoGateway(client, database="app")

    assert await gateway.ping() == {"ok": 1}
    await gateway.close()

    assert client.admin.commands == ["ping"]
    assert client.closed is True


async def test_check_mongo_connection_pings_gateway():
    client = _FakeClient()
    gateway = MongoGateway(client, database="app")

    await check_mongo_connection(gateway)

    assert client.admin.commands == ["ping"]


def test_build_mongo_gateway_uses_settings(monkeypatch, test_settings: Settings):
    client = _FakeClient()
    settings = test_settings.model_copy(
        update={
            "MONGODB_DATABASE": "product",
        }
    )

    monkeypatch.setattr(
        "app.modules.platform.mongo.factory.build_mongo_client",
        lambda received_settings: client,
    )

    gateway = build_mongo_gateway(settings)

    assert gateway.client is client
    assert gateway.database is client.databases["product"]


async def test_mongo_addon_opens_and_closes_gateway(
    monkeypatch, test_settings: Settings
):
    client = _FakeClient()
    settings = test_settings.model_copy(update={"MONGO_ENABLED": True})
    resources = ApplicationResources()
    addon = MongoAddon()

    monkeypatch.setattr(
        "app.modules.platform.mongo.factory.build_mongo_client",
        lambda received_settings: client,
    )

    assert addon.is_enabled(settings) is True
    await addon.open(FastAPI(), resources, settings)

    assert isinstance(resources.mongo, MongoGateway)
    assert resources.mongo.client is client

    await addon.close(FastAPI(), resources)

    assert resources.mongo is None
    assert client.closed is True


def test_get_mongo_dependency_returns_lifespan_resource():
    app = FastAPI()
    gateway = MongoGateway(_FakeClient(), database="app")
    app.state.resources = ApplicationResources(mongo=gateway)

    assert get_mongo(_request_for(app)) is gateway


def test_get_mongo_dependency_requires_configured_resource():
    app = FastAPI()
    app.state.resources = ApplicationResources()

    with pytest.raises(ServiceUnavailableError) as exc_info:
        get_mongo(_request_for(app))

    assert exc_info.value.code == "mongo_not_configured"
    assert exc_info.value.message == "MongoDB is not configured"
