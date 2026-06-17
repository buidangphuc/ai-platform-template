import pytest
from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.platform.objects.adapters.memory import MemoryObjectGateway
from app.modules.platform.objects.factory import ObjectAddon, build_object_gateway
from tests.factories import build_test_settings


def _settings(**overrides: object) -> Settings:
    return build_test_settings(**overrides)


def test_build_object_gateway_defaults_to_memory():
    gateway = build_object_gateway(_settings())

    assert isinstance(gateway, MemoryObjectGateway)


def test_s3_object_gateway_requires_bucket():
    with pytest.raises(RuntimeError, match="OBJECT_S3_BUCKET"):
        build_object_gateway(_settings(OBJECT_BACKEND="s3"))


async def test_object_addon_attaches_gateway_when_enabled():
    app = FastAPI()
    resources = ApplicationResources()
    addon = ObjectAddon()

    await addon.open(app, resources, _settings(OBJECTS_ENABLED=True))

    assert isinstance(resources.objects, MemoryObjectGateway)


def test_object_addon_respects_enabled_flag():
    addon = ObjectAddon()

    assert addon.is_enabled(_settings(OBJECTS_ENABLED=True)) is True
    assert addon.is_enabled(_settings(OBJECTS_ENABLED=False)) is False
