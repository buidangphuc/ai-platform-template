from app.bootstrap.addons.mongo import MongoAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.mongo.factory import (
    build_mongo_gateway,
    check_mongo_connection,
)
from app.modules.platform.mongo.gateway import MongoGateway
from tests.factories import open_addon


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
    stack = await open_addon(addon, resources, settings)

    assert isinstance(resources.mongo, MongoGateway)
    assert resources.mongo.client is client
    assert [name for name, _ in resources.health_checks.checks] == ["mongo"]

    await stack.aclose()

    assert client.closed is True
