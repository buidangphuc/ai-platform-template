import pytest
from fastapi import FastAPI

from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings
from app.modules.objects.adapters.memory import MemoryObjectGateway
from app.modules.objects.factory import ObjectAddon, build_object_gateway


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "_env_file": None,
        "ENVIRONMENT": "test",
        "POSTGRES_HOST": "localhost",
        "POSTGRES_USER": "postgres",
        "POSTGRES_PASSWORD": "postgres",  # pragma: allowlist secret
        "POSTGRES_DB": "ai_platform",
        "REDIS_HOST": "localhost",
        "AUTH_BEARER_TOKEN": "test-token",  # pragma: allowlist secret
    }
    base.update(overrides)
    return Settings(**base)


def test_build_object_gateway_defaults_to_memory():
    gateway = build_object_gateway(_settings())

    assert isinstance(gateway, MemoryObjectGateway)


def test_s3_object_gateway_requires_bucket():
    with pytest.raises(RuntimeError, match="OBJECT_S3_BUCKET"):
        build_object_gateway(_settings(OBJECT_BACKEND="s3"))


async def test_object_addon_attaches_gateway_when_enabled():
    app = FastAPI()
    addon = ObjectAddon()

    await addon.open(app, ApplicationResources(), _settings(OBJECTS_ENABLED=True))

    assert isinstance(app.state.objects, MemoryObjectGateway)


def test_object_addon_respects_enabled_flag():
    addon = ObjectAddon()

    assert addon.is_enabled(_settings(OBJECTS_ENABLED=True)) is True
    assert addon.is_enabled(_settings(OBJECTS_ENABLED=False)) is False
