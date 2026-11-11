"""Business-service composition: the one place business services are built.

Runs inside lifespan after platform resources are open, so a feature's ``build``
can take whatever it needs (LLM instance, RAG, stores) from ``resources``.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from app.bootstrap.addons.base import BootstrapAddon
from app.bootstrap.features.base import Feature, TaskHandler
from app.bootstrap.resources import ApplicationResources, open_application_resources
from app.core.config import Settings


def enabled_features(
    settings: Settings, features: tuple[Feature, ...]
) -> tuple[Feature, ...]:
    enabled = tuple(feature for feature in features if feature.enabled(settings))
    services: dict[type, str] = {}
    task_types: dict[str, str] = {}
    for feature in enabled:
        if feature.service in services:
            raise ValueError(
                f"service type {feature.service.__name__} registered by features "
                f"{services[feature.service]!r} and {feature.name!r}"
            )
        services[feature.service] = feature.name
        for task_type in feature.tasks:
            if task_type in task_types:
                raise ValueError(
                    f"task type {task_type!r} registered by features "
                    f"{task_types[task_type]!r} and {feature.name!r}"
                )
            task_types[task_type] = feature.name
    return enabled


def task_handlers(features: tuple[Feature, ...]) -> dict[str, TaskHandler]:
    return {
        task_type: handler
        for feature in features
        for task_type, handler in feature.tasks.items()
    }


def compose_business_services(
    resources: ApplicationResources,
    settings: Settings,
    features: tuple[Feature, ...],
) -> None:
    for feature in features:
        resources.services[feature.service] = feature.build(resources, settings)


@asynccontextmanager
async def open_runtime(
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...],
    features: tuple[Feature, ...],
) -> AsyncIterator[ApplicationResources]:
    """Open resources and compose business services; used by API and worker."""
    enabled = enabled_features(settings, features)
    async with open_application_resources(
        settings,
        init_resources=init_resources,
        addons=addons,
    ) as resources:
        compose_business_services(resources, settings, enabled)
        yield resources
