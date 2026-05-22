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

    def required_resources(self, settings: Settings) -> tuple[str, ...]:
        return ()

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

    assert addon.closed is True


async def test_disabled_resource_addon_is_skipped(test_settings: Settings):
    addon = _RecordingAddon(name="recording", enabled=False)
    app = create_app(
        settings=test_settings,
        init_resources=False,
        resource_addons=(addon,),
    )

    async with app.router.lifespan_context(app):
        assert addon.opened is False

    assert addon.closed is False


def test_bootstrap_addon_protocol_accepts_recording_addon():
    addon = _RecordingAddon(name="recording")

    assert isinstance(addon, BootstrapAddon)


async def test_enabled_resource_addon_fails_fast_when_required_core_resource_disabled(
    test_settings: Settings,
):
    @dataclass
    class _NeedsDatabaseAddon(_RecordingAddon):
        def required_resources(self, settings: Settings) -> tuple[str, ...]:
            return ("database",)

    addon = _NeedsDatabaseAddon(name="needs-db")
    settings = test_settings.model_copy(update={"DATABASE_ENABLED": False})
    app = create_app(
        settings=settings,
        init_resources=True,
        resource_addons=(addon,),
    )

    with pytest.raises(RuntimeError, match="Addon 'needs-db' requires database"):
        async with app.router.lifespan_context(app):
            pass

    assert addon.opened is False


async def test_disabled_resource_addon_does_not_validate_requirements(
    test_settings: Settings,
):
    @dataclass
    class _DisabledNeedsDatabaseAddon(_RecordingAddon):
        def required_resources(self, settings: Settings) -> tuple[str, ...]:
            return ("database",)

    addon = _DisabledNeedsDatabaseAddon(name="needs-db", enabled=False)
    settings = test_settings.model_copy(update={"DATABASE_ENABLED": False})
    app = create_app(
        settings=settings,
        init_resources=True,
        resource_addons=(addon,),
    )

    async with app.router.lifespan_context(app):
        assert addon.opened is False


async def test_legacy_resource_addon_without_requirements_method_still_opens(
    test_settings: Settings,
):
    class _LegacyAddon:
        name = "legacy"

        def __init__(self) -> None:
            self.opened = False

        def is_enabled(self, settings: Settings) -> bool:
            return True

        async def open(
            self,
            app: FastAPI,
            resources: ApplicationResources,
            settings: Settings,
        ) -> None:
            self.opened = True

        async def close(self, app: FastAPI, resources: ApplicationResources) -> None:
            return None

    addon = _LegacyAddon()
    app = create_app(
        settings=test_settings,
        init_resources=False,
        resource_addons=(addon,),  # type: ignore[arg-type]
    )

    async with app.router.lifespan_context(app):
        assert addon.opened is True
