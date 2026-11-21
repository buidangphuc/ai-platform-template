from __future__ import annotations

import importlib
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastapi import APIRouter

    from app.bootstrap.resources import ApplicationResources
    from app.core.config import Settings
    from app.modules.messaging.events.consumer import EventRecord
    from app.modules.messaging.tasks.store import TaskRecord
    from app.modules.platform.http.upstream import Upstream

TaskHandler = Callable[
    ["ApplicationResources", "TaskRecord"], Awaitable[dict[str, Any]]
]
ConsumerHandler = Callable[
    ["ApplicationResources", Sequence["EventRecord"]], Awaitable[None]
]


def _always(settings: Settings) -> bool:
    return True


def _no_consumers(settings: Settings) -> Mapping[str, ConsumerHandler]:
    return {}


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
    consumers: Callable[[Settings], Mapping[str, ConsumerHandler]] = _no_consumers


def import_models(features: tuple[Feature, ...]) -> None:
    for feature in features:
        for module in feature.models:
            importlib.import_module(module)
