from dataclasses import dataclass

from fastapi import FastAPI

from app.bootstrap.application import create_app
from app.bootstrap.manifest import build_bootstrap_manifest
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings


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


@dataclass
class _ManifestAddon:
    name: str = "manifest_addon"
    enabled: bool = True

    def is_enabled(self, settings: Settings) -> bool:
        return self.enabled

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ("database",)

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        return None

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        return None


def test_bootstrap_manifest_describes_effective_core_resources_and_addons():
    settings = _settings(REDIS_ENABLED=False, TASK_STORE_BACKEND="memory")

    manifest = build_bootstrap_manifest(
        settings=settings,
        init_resources=True,
        addons=(_ManifestAddon(),),
    )

    payload = manifest.to_dict()

    assert payload["init_resources"] is True
    assert payload["resources"]["database"] == {
        "name": "database",
        "enabled": True,
        "status": "planned",
        "backend": "postgres",
        "requires": [],
        "reason": None,
    }
    assert payload["resources"]["redis"]["enabled"] is False
    assert payload["resources"]["redis"]["status"] == "disabled"
    assert payload["resources"]["redis"]["reason"] == "REDIS_ENABLED=false"
    assert payload["resources"]["tasks"]["requires"] == ["queue"]
    assert payload["addons"] == [
        {
            "name": "manifest_addon",
            "enabled": True,
            "status": "planned",
            "backend": None,
            "requires": ["database"],
            "reason": None,
        }
    ]


def test_create_app_exposes_bootstrap_manifest_before_lifespan(
    test_settings: Settings,
):
    app = create_app(settings=test_settings, init_resources=False)

    manifest = app.state.bootstrap_manifest

    assert manifest.init_resources is False
    assert manifest.resources["database"].enabled is False
    assert manifest.resources["database"].reason == "init_resources=false"
    assert manifest.resources["queue"].status == "disabled"


async def test_bootstrap_manifest_tracks_open_and_close_statuses(
    monkeypatch,
    test_settings: Settings,
):
    from app.bootstrap import resources as resources_module

    class _Closable:
        async def close(self) -> None:
            return None

    class _Engine:
        async def dispose(self) -> None:
            return None

    class _Redis:
        async def aclose(self) -> None:
            return None

    monkeypatch.setattr(resources_module, "build_engine", lambda settings: _Engine())
    monkeypatch.setattr(
        resources_module,
        "build_sessionmaker",
        lambda engine: object(),
    )
    monkeypatch.setattr(
        resources_module,
        "build_redis_client",
        lambda settings: _Redis(),
    )
    monkeypatch.setattr(
        resources_module,
        "build_queue_gateway",
        lambda settings, *, redis=None: _Closable(),
    )
    monkeypatch.setattr(
        resources_module,
        "build_task_store",
        lambda settings, *, sessionmaker=None, redis=None: _Closable(),
    )

    app = create_app(settings=test_settings, init_resources=True)
    manifest = app.state.bootstrap_manifest

    assert manifest.resources["database"].status == "planned"

    async with app.router.lifespan_context(app):
        assert manifest.resources["database"].status == "opened"
        assert manifest.resources["redis"].status == "opened"
        assert manifest.resources["queue"].status == "opened"
        assert manifest.resources["tasks"].status == "opened"

    assert manifest.resources["database"].status == "closed"
    assert manifest.resources["redis"].status == "closed"
    assert manifest.resources["queue"].status == "closed"
    assert manifest.resources["tasks"].status == "closed"
