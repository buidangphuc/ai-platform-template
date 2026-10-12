"""Business-service composition: the one place business services are built.

Runs inside lifespan after platform resources are open, so a handler factory
can take whatever it needs (LLM instance, RAG, stores) from ``resources``.
"""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from app.bootstrap.addons.base import BootstrapAddon
from app.bootstrap.resources import ApplicationResources, open_application_resources
from app.core.config import Settings
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.service import CompletionService

CompletionHandlerFactory = Callable[[ApplicationResources, Settings], CompletionHandler]


def default_completion_handler_factory(
    resources: ApplicationResources,
    settings: Settings,
) -> CompletionHandler:
    """Scaffold handler; products pass their own factory to ``create_app``."""
    return EchoCompletionHandler()


def compose_business_services(
    resources: ApplicationResources,
    settings: Settings,
    *,
    completion_handler_factory: CompletionHandlerFactory,
) -> None:
    resources.completion_service = CompletionService(
        completion_handler_factory(resources, settings)
    )


@asynccontextmanager
async def open_runtime(
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...],
    completion_handler_factory: CompletionHandlerFactory,
) -> AsyncIterator[ApplicationResources]:
    """Open resources and compose business services; used by API and worker."""
    async with open_application_resources(
        settings,
        init_resources=init_resources,
        addons=addons,
    ) as resources:
        compose_business_services(
            resources,
            settings,
            completion_handler_factory=completion_handler_factory,
        )
        yield resources
