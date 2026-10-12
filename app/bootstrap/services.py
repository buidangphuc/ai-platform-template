"""Business-service composition: the one place business services are built.

Runs inside lifespan after platform resources are open, so a handler factory
can take whatever it needs (LLM instance, RAG, stores) from ``resources``.
"""

from collections.abc import Callable

from app.bootstrap.resources import ApplicationResources
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
