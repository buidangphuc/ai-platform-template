from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.bootstrap.addons import addon_required_resources
from app.core.config import Settings

if TYPE_CHECKING:
    from app.bootstrap.addons import BootstrapAddon


@dataclass
class BootstrapComponent:
    name: str
    enabled: bool
    status: str
    backend: str | None = None
    requires: tuple[str, ...] = ()
    reason: str | None = None

    def mark_opened(self) -> None:
        if self.enabled:
            self.status = "opened"

    def mark_closed(self) -> None:
        if self.status == "opened":
            self.status = "closed"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "enabled": self.enabled,
            "status": self.status,
            "backend": self.backend,
            "requires": list(self.requires),
            "reason": self.reason,
        }


@dataclass
class BootstrapManifest:
    init_resources: bool
    resources: dict[str, BootstrapComponent]
    addons: list[BootstrapComponent]

    def mark_resource_opened(self, name: str) -> None:
        self.resources[name].mark_opened()

    def mark_resource_closed(self, name: str) -> None:
        self.resources[name].mark_closed()

    def mark_addon_opened(self, name: str) -> None:
        for addon in self.addons:
            if addon.name == name:
                addon.mark_opened()
                return

    def mark_addon_closed(self, name: str) -> None:
        for addon in self.addons:
            if addon.name == name:
                addon.mark_closed()
                return

    def to_dict(self) -> dict[str, Any]:
        return {
            "init_resources": self.init_resources,
            "resources": {
                name: component.to_dict() for name, component in self.resources.items()
            },
            "addons": [addon.to_dict() for addon in self.addons],
        }


def build_bootstrap_manifest(
    *,
    settings: Settings,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...],
) -> BootstrapManifest:
    resources = {
        "database": _core_component(
            "database",
            init_resources=init_resources,
            flag_enabled=settings.DATABASE_ENABLED,
            flag_name="DATABASE_ENABLED",
            backend="postgres",
        ),
        "redis": _core_component(
            "redis",
            init_resources=init_resources,
            flag_enabled=settings.REDIS_ENABLED,
            flag_name="REDIS_ENABLED",
            backend="redis",
        ),
        "queue": _core_component(
            "queue",
            init_resources=init_resources,
            flag_enabled=settings.QUEUE_ENABLED,
            flag_name="QUEUE_ENABLED",
            backend=settings.QUEUE_BACKEND,
            requires=_queue_requires(settings),
        ),
        "tasks": _core_component(
            "tasks",
            init_resources=init_resources,
            flag_enabled=settings.TASKS_ENABLED,
            flag_name="TASKS_ENABLED",
            backend=settings.TASK_STORE_BACKEND,
            requires=_tasks_requires(settings),
        ),
    }
    return BootstrapManifest(
        init_resources=init_resources,
        resources=resources,
        addons=[
            _addon_component(addon, settings=settings, init_resources=init_resources)
            for addon in addons
        ],
    )


def _core_component(
    name: str,
    *,
    init_resources: bool,
    flag_enabled: bool,
    flag_name: str,
    backend: str,
    requires: tuple[str, ...] = (),
) -> BootstrapComponent:
    enabled = init_resources and flag_enabled
    reason = None
    if not init_resources:
        reason = "init_resources=false"
    elif not flag_enabled:
        reason = f"{flag_name}=false"
    return BootstrapComponent(
        name=name,
        enabled=enabled,
        status="planned" if enabled else "disabled",
        backend=backend,
        requires=requires,
        reason=reason,
    )


def _addon_component(
    addon: BootstrapAddon,
    *,
    settings: Settings,
    init_resources: bool,
) -> BootstrapComponent:
    flag_enabled = addon.is_enabled(settings)
    enabled = init_resources and flag_enabled
    reason = None
    if not init_resources:
        reason = "init_resources=false"
    elif not flag_enabled:
        reason = "addon disabled"
    return BootstrapComponent(
        name=addon.name,
        enabled=enabled,
        status="planned" if enabled else "disabled",
        requires=addon_required_resources(addon, settings),
        reason=reason,
    )


def _queue_requires(settings: Settings) -> tuple[str, ...]:
    return ("redis",) if settings.QUEUE_BACKEND == "redis" else ()


def _tasks_requires(settings: Settings) -> tuple[str, ...]:
    requires = ["queue"]
    if settings.TASK_STORE_BACKEND == "postgres":
        requires.append("database")
    if settings.TASK_STORE_BACKEND == "redis":
        requires.append("redis")
    return tuple(requires)
