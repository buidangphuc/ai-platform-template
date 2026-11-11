from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter

    from app.bootstrap.resources import ApplicationResources
    from app.core.config import Settings
    from app.modules.messaging.tasks.store import TaskRecord
    from app.modules.platform.http.upstream import Upstream

TaskHandler = Callable[
    ["ApplicationResources", "TaskRecord"], Awaitable[dict[str, Any]]
]


def _always(settings: Settings) -> bool:
    return True


@dataclass(frozen=True)
class Feature:
    name: str
    service: type[Any]
    build: Callable[[ApplicationResources, Settings], Any]
    routers: tuple[APIRouter, ...] = ()
    task_routers: tuple[APIRouter, ...] = ()
    tasks: Mapping[str, TaskHandler] = field(default_factory=dict)
    models: tuple[str, ...] = ()
    upstreams: tuple[Upstream, ...] = ()
    enabled: Callable[[Settings], bool] = _always


def import_models(features: tuple[Feature, ...]) -> None:
    for feature in features:
        for module in feature.models:
            importlib.import_module(module)
