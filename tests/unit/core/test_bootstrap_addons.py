from dataclasses import dataclass

import pytest
from fastapi import FastAPI

from app.bootstrap.addons import BootstrapAddon
from app.bootstrap.application import create_app
from app.bootstrap.resources import ApplicationResources
from app.core.config import Settings


@dataclass
class _RecordingAddon:
    name: str
    enabled: bool = True
    opened: bool = False
    closed: bool = False

    def is_enabled(self, settings: Settings) -> bool:
        return self.enabled

    async def open(
        self,
        app: FastAPI,
        resources: ApplicationResources,
        settings: Settings,
    ) -> None:
        self.opened = True
        app.state.addon_resource = self.name

    async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
        self.closed = True


async def test_resource_addon_opens_only_inside_lifespan(test_settings: Settings):
    addon = _RecordingAddon(name="recording")
    app = create_app(
        settings=test_settings,
        init_resources=False,
        resource_addons=(addon,),
    )

    assert addon.opened is False
    assert not hasattr(app.state, "addon_resource")

    async with app.router.lifespan_context(app):
        assert addon.opened is True
        assert addon.closed is False
        assert app.state.addon_resource == "recording"
        assert addon in app.state.resources.addons

    assert addon.closed is True
    assert app.state.resources.addons == []


async def test_disabled_resource_addon_is_skipped(test_settings: Settings):
    addon = _RecordingAddon(name="recording", enabled=False)
    app = create_app(
        settings=test_settings,
        init_resources=False,
        resource_addons=(addon,),
    )

    async with app.router.lifespan_context(app):
        assert addon.opened is False
        assert addon not in app.state.resources.addons

    assert addon.closed is False


def test_bootstrap_addon_protocol_accepts_recording_addon():
    addon = _RecordingAddon(name="recording")

    assert isinstance(addon, BootstrapAddon)


async def test_addon_self_validates_required_resources_in_open(
    test_settings: Settings,
):
    @dataclass
    class _NeedsDatabaseAddon(_RecordingAddon):
        async def open(
            self,
            app: FastAPI,
            resources: ApplicationResources,
            settings: Settings,
        ) -> None:
            if not settings.DATABASE_ENABLED:
                raise RuntimeError("NeedsDatabaseAddon requires DATABASE_ENABLED")
            await super().open(app, resources, settings)

    addon = _NeedsDatabaseAddon(name="needs-db")
    settings = test_settings.model_copy(update={"DATABASE_ENABLED": False})
    app = create_app(
        settings=settings,
        init_resources=True,
        resource_addons=(addon,),
    )

    with pytest.raises(
        RuntimeError, match="NeedsDatabaseAddon requires DATABASE_ENABLED"
    ):
        async with app.router.lifespan_context(app):
            pass

    assert addon.opened is False


async def test_disabled_addon_skips_self_validation(
    test_settings: Settings,
):
    @dataclass
    class _DisabledNeedsDatabaseAddon(_RecordingAddon):
        async def open(
            self,
            app: FastAPI,
            resources: ApplicationResources,
            settings: Settings,
        ) -> None:
            if not settings.DATABASE_ENABLED:
                raise RuntimeError("should not be reached when disabled")
            await super().open(app, resources, settings)

    addon = _DisabledNeedsDatabaseAddon(name="needs-db", enabled=False)
    settings = test_settings.model_copy(update={"DATABASE_ENABLED": False})
    app = create_app(
        settings=settings,
        init_resources=True,
        resource_addons=(addon,),
    )

    async with app.router.lifespan_context(app):
        assert addon.opened is False
