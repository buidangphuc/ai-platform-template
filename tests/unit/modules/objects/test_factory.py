from fastapi import FastAPI

from app.bootstrap.addons.objects import ObjectAddon
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.objects.adapters.memory import MemoryObjectGateway
from app.modules.platform.objects.factory import open_object_gateway
from tests.factories import build_test_settings, open_addon


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


async def test_open_object_gateway_defaults_to_memory():
    gateway = await open_object_gateway(_settings())

    assert isinstance(gateway, MemoryObjectGateway)


async def test_object_addon_attaches_gateway_when_enabled():
    FastAPI()
    resources = ApplicationResources()
    addon = ObjectAddon()

    stack = await open_addon(addon, resources, _settings(OBJECTS_ENABLED=True))

    assert isinstance(resources.objects, MemoryObjectGateway)

    await stack.aclose()


def test_object_addon_respects_enabled_flag():
    addon = ObjectAddon()

    assert addon.is_enabled(_settings(OBJECTS_ENABLED=True)) is True
    assert addon.is_enabled(_settings(OBJECTS_ENABLED=False)) is False
