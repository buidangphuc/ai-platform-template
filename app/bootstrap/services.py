"""Business-service composition: the one place business services are built.

Runs inside lifespan after platform resources are open, so a handler factory
can take whatever it needs (LLM instance, RAG, stores) from ``resources``.
"""

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager

from app.bootstrap.addons.base import BootstrapAddon
from app.bootstrap.resources import ApplicationResources, open_application_resources
from app.core.config import Settings
from app.core.telemetry import (
    CompletionObservation,
    FanOutSink,
    LogCompletionSink,
)
from app.modules.business.completions.guards import CompletionGuard
from app.modules.business.completions.handlers.echo import EchoCompletionHandler
from app.modules.business.completions.ports import CompletionHandler
from app.modules.business.completions.service import (
    CompletionService,
    StreamPolicy,
)

CompletionHandlerFactory = Callable[[ApplicationResources, Settings], CompletionHandler]
CompletionGuardsFactory = Callable[
    [ApplicationResources, Settings], Sequence[CompletionGuard]
]


def default_completion_guards_factory(
    resources: ApplicationResources,
    settings: Settings,
) -> Sequence[CompletionGuard]:
    """Scaffold ships no guards; products add theirs (input/output checks)."""
    return ()


def default_completion_handler_factory(
    resources: ApplicationResources,
    settings: Settings,
) -> CompletionHandler:
    """Scaffold handler; products pass their own factory to ``create_app``."""
    return EchoCompletionHandler()


class _ResourceTelemetry:
    """The OTel handle, resolved per record: it exists only when OTEL_ENABLED."""

    def __init__(self, resources: ApplicationResources) -> None:
        self.resources = resources

    def record_completion(self, observation: CompletionObservation) -> None:
        if self.resources.telemetry:
            self.resources.telemetry.record_completion(observation)


def compose_business_services(
    resources: ApplicationResources,
    settings: Settings,
    *,
    completion_handler_factory: CompletionHandlerFactory,
    completion_guards_factory: CompletionGuardsFactory,
) -> None:
    resources.completion_service = CompletionService(
        completion_handler_factory(resources, settings),
        guards=completion_guards_factory(resources, settings),
        sink=FanOutSink([LogCompletionSink(), _ResourceTelemetry(resources)]),
        policy=StreamPolicy(
            first_token_timeout=settings.STREAM_FIRST_TOKEN_TIMEOUT_SECONDS,
            idle_timeout=settings.STREAM_IDLE_TIMEOUT_SECONDS,
        ),
    )


@asynccontextmanager
async def open_runtime(
    settings: Settings,
    *,
    init_resources: bool,
    addons: tuple[BootstrapAddon, ...],
    completion_handler_factory: CompletionHandlerFactory,
    completion_guards_factory: CompletionGuardsFactory,
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
            completion_guards_factory=completion_guards_factory,
        )
        yield resources
